"""
Celery task definitions for background/scheduled ingest runs.

STATUS: written but UNTESTED -- there is no Redis (or other broker)
running in this environment, and Docker is not installed here, so this
module has never been exercised end-to-end against a live worker. See
BLOCKERS.md for what a human needs to do to unblock it (run
`docker compose up redis` from infra/, or point CELERY_BROKER_URL at
any reachable Redis instance).

The synchronous code path (app.ingest.run_ingest) that these tasks
wrap IS fully tested and does run today -- this file only adds a thin
Celery wrapper + a periodic beat schedule around it so ingest runs can
be automated once a broker exists, without needing any code changes
to the ingest logic itself.
"""
from __future__ import annotations

import logging
import os

from celery import Celery
from celery.schedules import crontab

from app.db import SessionLocal
from app.ingest import run_ingest
from app.models import Jurisdiction
from app.scoring.service import compute_scores_for_permit_ids

logger = logging.getLogger(__name__)

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)

celery_app = Celery(
    "construction_intel",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Periodic schedule: re-ingest every active jurisdiction every 6 hours.
# Requires `celery -A app.tasks worker --loglevel=info` AND
# `celery -A app.tasks beat --loglevel=info` running against a live
# broker -- neither is running in this dev environment.
celery_app.conf.beat_schedule = {
    "ingest-all-active-jurisdictions-every-6-hours": {
        "task": "app.tasks.ingest_all_active_jurisdictions",
        "schedule": crontab(minute=0, hour="*/6"),
    },
}


@celery_app.task(name="app.tasks.ingest_jurisdiction", bind=True, max_retries=3, default_retry_delay=60)
def ingest_jurisdiction_task(self, jurisdiction_id: int, limit: int | None = None):
    """Run a single jurisdiction's connector and persist results + scores."""
    db = SessionLocal()
    try:
        jurisdiction = db.query(Jurisdiction).filter(Jurisdiction.id == jurisdiction_id).one_or_none()
        if jurisdiction is None:
            logger.error("ingest_jurisdiction_task: jurisdiction %s not found", jurisdiction_id)
            return {"error": "jurisdiction not found"}

        stats = run_ingest(db, jurisdiction, limit=limit)
        scored = compute_scores_for_permit_ids(db, stats.touched_permit_ids)
        return {
            "jurisdiction_id": jurisdiction_id,
            "fetched": stats.fetched,
            "created": stats.created,
            "updated": stats.updated,
            "unchanged": stats.unchanged,
            "errors": stats.errors,
            "scored": scored,
        }
    except Exception as exc:  # pragma: no cover - retry path, exercised only with a live broker
        logger.exception("ingest_jurisdiction_task failed for jurisdiction %s", jurisdiction_id)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(name="app.tasks.ingest_all_active_jurisdictions")
def ingest_all_active_jurisdictions():
    """Fan out an ingest task for every active jurisdiction."""
    db = SessionLocal()
    try:
        jurisdiction_ids = [j.id for j in db.query(Jurisdiction).filter(Jurisdiction.is_active.is_(True)).all()]
    finally:
        db.close()

    for jurisdiction_id in jurisdiction_ids:
        ingest_jurisdiction_task.delay(jurisdiction_id)

    return {"queued": len(jurisdiction_ids)}
