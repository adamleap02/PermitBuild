from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Permit
from app.routers.permits import apply_filters

router = APIRouter(prefix="/export", tags=["export"])

CSV_COLUMNS = [
    "id",
    "jurisdiction_id",
    "permit_number",
    "permit_type",
    "status",
    "application_date",
    "issue_date",
    "completion_date",
    "expiration_date",
    "contractor",
    "builder",
    "architect",
    "engineer",
    "property_address",
    "parcel_number",
    "estimated_cost",
    "valuation",
    "description",
    "work_category",
    "square_footage",
    "units",
    "latitude",
    "longitude",
    "permit_url",
    "source",
]


@router.get("")
def export_permits_csv(
    jurisdiction_id: Optional[int] = None,
    permit_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    keyword: Optional[str] = None,
    limit: int = Query(default=5000, ge=1, le=50000),
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
    permits = query.order_by(Permit.id.asc()).limit(limit).all()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for permit in permits:
        row = {col: getattr(permit, col, None) for col in CSV_COLUMNS}
        writer.writerow(row)
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=permits_export.csv"},
    )
