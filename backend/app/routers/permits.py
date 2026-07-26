from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import nullslast, or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Permit, PermitVersion, Score
from app.schemas import (
    PermitDetail,
    PermitListResponse,
    PermitMapResponse,
    PermitVersionOut,
    ScoreOut,
)

router = APIRouter(prefix="/permits", tags=["permits"])


def apply_filters(
    query,
    jurisdiction_id: Optional[int] = None,
    permit_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    keyword: Optional[str] = None,
):
    if jurisdiction_id is not None:
        query = query.filter(Permit.jurisdiction_id == jurisdiction_id)
    if permit_type is not None:
        query = query.filter(Permit.permit_type.ilike(f"%{permit_type}%"))
    if status is not None:
        query = query.filter(Permit.status.ilike(f"%{status}%"))
    if date_from is not None:
        query = query.filter(Permit.issue_date >= date_from)
    if date_to is not None:
        query = query.filter(Permit.issue_date <= date_to)
    if min_value is not None:
        query = query.filter(
            or_(Permit.valuation >= min_value, Permit.estimated_cost >= min_value)
        )
    if max_value is not None:
        query = query.filter(
            or_(Permit.valuation <= max_value, Permit.estimated_cost <= max_value)
        )
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            or_(
                Permit.description.ilike(like),
                Permit.property_address.ilike(like),
                Permit.permit_number.ilike(like),
                Permit.contractor.ilike(like),
            )
        )
    return query


@router.get("", response_model=PermitListResponse)
def search_permits(
    jurisdiction_id: Optional[int] = None,
    permit_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    keyword: Optional[str] = Query(default=None, description="Full-text-ish search over description/address/permit number/contractor"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Permit)
    query = apply_filters(
        query,
        jurisdiction_id=jurisdiction_id,
        permit_type=permit_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        min_value=min_value,
        max_value=max_value,
        keyword=keyword,
    )
    total = query.count()
    items = (
        query.order_by(nullslast(Permit.issue_date.desc()), Permit.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PermitListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/map", response_model=PermitMapResponse)
def map_permits(
    jurisdiction_id: Optional[int] = None,
    permit_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    keyword: Optional[str] = None,
    limit: int = Query(
        default=600000,
        ge=1,
        le=1000000,
        description="Max geocoded points to return for map rendering. Defaults high enough to cover every geocoded permit in the dataset; client-side supercluster clustering is designed for this scale.",
    ),
    db: Session = Depends(get_db),
):
    """Lightweight, high-volume endpoint for the map view -- unlike the
    paginated /permits list (capped at 200/page for tables), this returns
    up to `limit` geocoded points matching the same filters so the map can
    reflect the real scale of the dataset. Clustering happens client-side
    (MapLibre supercluster), so a few thousand points render fine."""
    query = db.query(Permit)
    query = apply_filters(
        query,
        jurisdiction_id=jurisdiction_id,
        permit_type=permit_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        min_value=min_value,
        max_value=max_value,
        keyword=keyword,
    )
    total_matching = query.count()

    geocoded_query = query.filter(Permit.latitude.isnot(None), Permit.longitude.isnot(None))
    total_geocoded = geocoded_query.count()

    items = (
        geocoded_query.order_by(nullslast(Permit.issue_date.desc()), Permit.id.desc())
        .limit(limit)
        .all()
    )
    return PermitMapResponse(
        total_matching=total_matching,
        total_geocoded=total_geocoded,
        returned=len(items),
        items=items,
    )


@router.get("/{permit_id}", response_model=PermitDetail)
def get_permit(permit_id: int, db: Session = Depends(get_db)):
    permit = db.query(Permit).filter(Permit.id == permit_id).one_or_none()
    if permit is None:
        raise HTTPException(status_code=404, detail="Permit not found")

    versions = (
        db.query(PermitVersion)
        .filter(PermitVersion.permit_id == permit_id)
        .order_by(PermitVersion.version_number.asc())
        .all()
    )
    latest_score = (
        db.query(Score)
        .filter(Score.permit_id == permit_id)
        .order_by(Score.computed_at.desc())
        .first()
    )

    detail = PermitDetail.model_validate(permit)
    detail.versions = [PermitVersionOut.model_validate(v) for v in versions]
    if latest_score is not None:
        detail.latest_score = ScoreOut.model_validate(latest_score)
    return detail
