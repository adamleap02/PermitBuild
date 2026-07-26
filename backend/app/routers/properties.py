from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Property
from app.schemas import PropertyOut

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("/{property_id}", response_model=PropertyOut)
def get_property(property_id: int, db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id).one_or_none()
    if prop is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop
