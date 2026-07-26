from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.ingest import run_ingest
from app.models import Jurisdiction
from app.schemas import IngestRunRequest, IngestRunResponse
from app.scoring.service import compute_scores_for_permit_ids

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/run", response_model=IngestRunResponse)
def trigger_ingest(payload: IngestRunRequest, db: Session = Depends(get_db)):
    jurisdiction = db.query(Jurisdiction).filter(Jurisdiction.id == payload.jurisdiction_id).one_or_none()
    if jurisdiction is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")

    try:
        stats = run_ingest(db, jurisdiction, since=payload.since, limit=payload.limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ingest failed: {exc}") from exc

    scored = 0
    if payload.compute_scores:
        scored = compute_scores_for_permit_ids(db, stats.touched_permit_ids)

    return IngestRunResponse(
        jurisdiction_id=jurisdiction.id,
        jurisdiction_name=jurisdiction.name,
        fetched=stats.fetched,
        created=stats.created,
        updated=stats.updated,
        unchanged=stats.unchanged,
        errors=stats.errors,
        scored=scored,
    )
