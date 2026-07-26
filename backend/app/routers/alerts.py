from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.alerts.service import run_alert
from app.db import get_db
from app.models import Alert, AlertChannel, AlertFrequency, SavedSearch, User
from app.schemas import AlertCreate, AlertOut, AlertRunResult
from app.security import get_current_user

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("", response_model=AlertOut, status_code=201)
def create_alert(
    payload: AlertCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    saved_search = (
        db.query(SavedSearch)
        .filter(
            SavedSearch.id == payload.saved_search_id,
            SavedSearch.organization_id == current_user.organization_id,
        )
        .one_or_none()
    )
    if saved_search is None:
        raise HTTPException(status_code=404, detail="Saved search not found")

    try:
        channel = AlertChannel(payload.channel)
        frequency = AlertFrequency(payload.frequency)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    alert = Alert(
        saved_search_id=saved_search.id,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        channel=channel,
        recipient=payload.recipient,
        frequency=frequency,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


@router.get("", response_model=list[AlertOut])
def list_alerts(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Alert)
        .filter(Alert.organization_id == current_user.organization_id)
        .order_by(Alert.created_at.desc())
        .all()
    )


@router.delete("/{alert_id}", status_code=204)
def delete_alert(alert_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    alert = _get_owned_alert(db, alert_id, current_user)
    db.delete(alert)
    db.commit()
    return None


@router.post("/{alert_id}/run", response_model=AlertRunResult)
def run_alert_now(alert_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Manually trigger a single alert's check-and-notify cycle.

    There is no background scheduler running in this environment (see
    BLOCKERS.md re: Celery/Redis) -- this endpoint is the synchronous,
    fully-working stand-in for what a periodic Celery beat task would
    otherwise call automatically once a broker exists.
    """
    alert = _get_owned_alert(db, alert_id, current_user)
    if not alert.is_active:
        raise HTTPException(status_code=400, detail="Alert is not active")
    result = run_alert(db, alert)
    return AlertRunResult(**result)


def _get_owned_alert(db: Session, alert_id: int, current_user: User) -> Alert:
    alert = (
        db.query(Alert)
        .filter(Alert.id == alert_id, Alert.organization_id == current_user.organization_id)
        .one_or_none()
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert
