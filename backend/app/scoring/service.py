"""Glue between the pure-function scoring engine and the DB: computes
scores for permits and persists them as Score rows."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Permit, Score
from app.scoring.engine import score_permit


def compute_and_store_score(db: Session, permit: Permit) -> Score:
    result = score_permit(permit)
    score = Score(permit_id=permit.id, **result.as_dict())
    db.add(score)
    return score


def compute_scores_for_permit_ids(db: Session, permit_ids: list[int]) -> int:
    if not permit_ids:
        return 0
    permits = db.query(Permit).filter(Permit.id.in_(permit_ids)).all()
    for permit in permits:
        compute_and_store_score(db, permit)
    db.commit()
    return len(permits)
