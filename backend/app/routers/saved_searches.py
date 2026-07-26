from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SavedSearch, User
from app.schemas import SavedSearchCreate, SavedSearchOut
from app.security import get_current_user

router = APIRouter(prefix="/saved-searches", tags=["saved-searches"])


@router.post("", response_model=SavedSearchOut, status_code=201)
def create_saved_search(
    payload: SavedSearchCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    saved_search = SavedSearch(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        name=payload.name,
        filters=payload.filters,
    )
    db.add(saved_search)
    db.commit()
    db.refresh(saved_search)
    return saved_search


@router.get("", response_model=list[SavedSearchOut])
def list_saved_searches(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(SavedSearch)
        .filter(SavedSearch.organization_id == current_user.organization_id)
        .order_by(SavedSearch.created_at.desc())
        .all()
    )


@router.get("/{saved_search_id}", response_model=SavedSearchOut)
def get_saved_search(
    saved_search_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    saved_search = _get_owned_saved_search(db, saved_search_id, current_user)
    return saved_search


@router.delete("/{saved_search_id}", status_code=204)
def delete_saved_search(
    saved_search_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    saved_search = _get_owned_saved_search(db, saved_search_id, current_user)
    db.delete(saved_search)
    db.commit()
    return None


def _get_owned_saved_search(db: Session, saved_search_id: int, current_user: User) -> SavedSearch:
    saved_search = (
        db.query(SavedSearch)
        .filter(SavedSearch.id == saved_search_id, SavedSearch.organization_id == current_user.organization_id)
        .one_or_none()
    )
    if saved_search is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return saved_search
