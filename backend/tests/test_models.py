from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Jurisdiction,
    Owner,
    Permit,
    PermitVersion,
    Property,
    Score,
    SourceSystem,
)


def _make_jurisdiction(db_session, name="Testville", state="TX"):
    j = Jurisdiction(
        name=name,
        state=state,
        level="city",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "example.data.socrata.com", "dataset_id": "abcd-1234"},
    )
    db_session.add(j)
    db_session.commit()
    db_session.refresh(j)
    return j


def test_create_jurisdiction_and_permit(db_session):
    j = _make_jurisdiction(db_session)

    permit = Permit(
        jurisdiction_id=j.id,
        permit_number="P-0001",
        permit_type="Residential Addition",
        estimated_cost=50000.0,
        property_address="100 Main St",
    )
    db_session.add(permit)
    db_session.commit()
    db_session.refresh(permit)

    assert permit.id is not None
    assert permit.jurisdiction.name == "Testville"
    assert permit.created_at is not None
    assert permit.updated_at is not None


def test_permit_unique_constraint_per_jurisdiction(db_session):
    j = _make_jurisdiction(db_session, name="UniqueTown", state="CA")
    db_session.add(Permit(jurisdiction_id=j.id, permit_number="DUP-1"))
    db_session.commit()

    db_session.add(Permit(jurisdiction_id=j.id, permit_number="DUP-1"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_permit_version_append_only_history(db_session):
    j = _make_jurisdiction(db_session, name="Versionville", state="NY")
    permit = Permit(jurisdiction_id=j.id, permit_number="V-1", status="Filed")
    db_session.add(permit)
    db_session.commit()
    db_session.refresh(permit)

    v1 = PermitVersion(permit_id=permit.id, version_number=1, snapshot={"status": "Filed"}, changed_fields={})
    db_session.add(v1)
    db_session.commit()

    permit.status = "Issued"
    v2 = PermitVersion(
        permit_id=permit.id,
        version_number=2,
        snapshot={"status": "Issued"},
        changed_fields={"status": {"old": "Filed", "new": "Issued"}},
    )
    db_session.add(v2)
    db_session.commit()

    versions = (
        db_session.query(PermitVersion)
        .filter(PermitVersion.permit_id == permit.id)
        .order_by(PermitVersion.version_number)
        .all()
    )
    assert [v.version_number for v in versions] == [1, 2]
    assert versions[0].snapshot["status"] == "Filed"
    assert versions[1].changed_fields["status"]["new"] == "Issued"


def test_property_owner_and_score_relationships(db_session):
    j = _make_jurisdiction(db_session, name="Relationville", state="FL")
    prop = Property(address="200 Oak Ave", normalized_address="200 OAK AVE", latitude=1.0, longitude=2.0)
    db_session.add(prop)
    db_session.commit()
    db_session.refresh(prop)

    owner = Owner(property_id=prop.id, name="Jane Doe", owner_type="individual")
    db_session.add(owner)

    permit = Permit(
        jurisdiction_id=j.id,
        permit_number="R-1",
        property_id=prop.id,
        estimated_cost=10000.0,
    )
    db_session.add(permit)
    db_session.commit()
    db_session.refresh(permit)

    score = Score(
        permit_id=permit.id,
        project_size_score=10.0,
        project_size_explanation="x",
        budget_tier="small",
        budget_tier_explanation="x",
        urgency_score=0.0,
        urgency_explanation="x",
        luxury_likelihood=0.0,
        luxury_explanation="x",
        remodel_vs_repair="repair",
        remodel_vs_repair_explanation="x",
        investment_property_likelihood=0.0,
        investment_property_explanation="x",
        lead_score=5.0,
        lead_score_explanation="x",
        confidence_score=50.0,
        confidence_explanation="x",
    )
    db_session.add(score)
    db_session.commit()

    db_session.refresh(prop)
    db_session.refresh(permit)
    assert prop.owners[0].name == "Jane Doe"
    assert permit.property.id == prop.id
    assert permit.scores[0].lead_score == 5.0
