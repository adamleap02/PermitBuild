from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Jurisdiction, SourceSystem
from app.schemas import JurisdictionCreate, JurisdictionOut

router = APIRouter(prefix="/jurisdictions", tags=["jurisdictions"])


@router.get("", response_model=list[JurisdictionOut])
def list_jurisdictions(db: Session = Depends(get_db)):
    return db.query(Jurisdiction).order_by(Jurisdiction.id.asc()).all()


@router.post("", response_model=JurisdictionOut, status_code=201)
def create_jurisdiction(payload: JurisdictionCreate, db: Session = Depends(get_db)):
    try:
        source_system = SourceSystem(payload.source_system)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid source_system: {payload.source_system}") from exc

    existing = (
        db.query(Jurisdiction)
        .filter(Jurisdiction.name == payload.name, Jurisdiction.state == payload.state)
        .one_or_none()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Jurisdiction with this name/state already exists")

    jurisdiction = Jurisdiction(
        name=payload.name,
        state=payload.state,
        level=payload.level,
        timezone=payload.timezone,
        source_system=source_system,
        source_config=payload.source_config,
    )
    db.add(jurisdiction)
    db.commit()
    db.refresh(jurisdiction)
    return jurisdiction


@router.get("/{jurisdiction_id}", response_model=JurisdictionOut)
def get_jurisdiction(jurisdiction_id: int, db: Session = Depends(get_db)):
    jurisdiction = db.query(Jurisdiction).filter(Jurisdiction.id == jurisdiction_id).one_or_none()
    if jurisdiction is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    return jurisdiction
