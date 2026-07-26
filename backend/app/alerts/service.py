"""Runs a single Alert: finds permits matching its SavedSearch's filters
that are new/changed since the alert was last checked, and delivers
(via the stubbed notifier) a summary."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.alerts.notifier import get_channel
from app.models import Alert, Permit
from app.routers.permits import apply_filters


def run_alert(db: Session, alert: Alert) -> dict:
    saved_search = alert.saved_search
    filters = saved_search.filters or {}

    query = db.query(Permit)
    query = apply_filters(
        query,
        jurisdiction_id=filters.get("jurisdiction_id"),
        permit_type=filters.get("permit_type"),
        status=filters.get("status"),
        date_from=filters.get("date_from"),
        date_to=filters.get("date_to"),
        min_value=filters.get("min_value"),
        max_value=filters.get("max_value"),
        keyword=filters.get("keyword"),
    )

    # Only notify about permits created/updated since the last check --
    # first run (last_checked_at is None) notifies on everything currently
    # matching, capped, so a brand-new alert doesn't silently no-op.
    if alert.last_checked_at is not None:
        query = query.filter(Permit.updated_at >= alert.last_checked_at)

    permits = query.order_by(Permit.updated_at.desc()).limit(200).all()

    channel = get_channel(alert.channel.value if hasattr(alert.channel, "value") else alert.channel)
    result = channel.send(db, alert, permits)

    alert.last_checked_at = datetime.now(timezone.utc)
    db.add(alert)
    db.commit()

    return {
        "alert_id": alert.id,
        "matched_permits": len(permits),
        "delivery_status": result.status,
        "delivery_log_id": result.log_id,
    }
