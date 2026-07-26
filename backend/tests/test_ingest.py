"""
Regression tests for app/ingest.py's version-numbering path.

The bug (BLOCKERS.md §5i): when the same ``permit_number`` appears more
than once inside a single fetch batch (common on non-unique-permit-number
feeds), the next ``version_number`` was recomputed from a DB query that --
because the session runs with ``autoflush=False`` (app/db.py) -- could not
see the PermitVersion added a moment earlier in the same uncommitted batch.
Both occurrences computed the same "next" number and collided on the
``(permit_id, version_number)`` UNIQUE constraint at ``commit()`` time,
failing the whole jurisdiction (SF, Cincinnati) or the record (Marin,
Howard, Minneapolis, Nashville, Fort Worth).

These tests reproduce that exact shape (a batch with a repeated
permit_number) and assert the commit no longer raises an IntegrityError,
and that sequential, gap-free version numbers are produced.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app import ingest as ingest_module
from app.connectors.base import PermitConnector
from app.ingest import run_ingest
from app.models import Jurisdiction, Permit, PermitVersion, SourceSystem


class _FakeConnector(PermitConnector):
    """A connector that yields a fixed, in-memory list of normalized dicts
    (no network) -- lets us drive run_ingest with a controlled batch."""

    source_system = "manual"

    def __init__(self, records):
        self._records = records

    def discover(self):  # pragma: no cover - not used in these tests
        raise NotImplementedError

    def fetch_permits(self, since=None, limit=None):
        records = self._records if limit is None else self._records[:limit]
        for rec in records:
            yield dict(rec)


def _permit(permit_number, **overrides):
    rec = {k: None for k in ingest_module.NORMALIZED_PERMIT_FIELDS}
    rec["permit_number"] = permit_number
    rec["raw_data"] = {}
    rec.update(overrides)
    return rec


@pytest.fixture()
def jurisdiction(db_session):
    j = Jurisdiction(
        name="Testville",
        state="TX",
        level="city",
        timezone="UTC",
        source_system=SourceSystem.MANUAL,
        source_config={},
    )
    db_session.add(j)
    db_session.commit()
    db_session.refresh(j)
    return j


def _run(db, jurisdiction, records, monkeypatch):
    monkeypatch.setattr(ingest_module, "build_connector", lambda _j: _FakeConnector(records))
    # No geocoding / enrichment -> no network, deterministic.
    return run_ingest(db, jurisdiction, geocode_missing=False, enrich=False)


def test_duplicate_permit_number_in_one_batch_created_path(db_session, jurisdiction, monkeypatch):
    """Same permit_number twice in the FIRST-ever batch (both hit the
    create-then-update path). Pre-fix this raised IntegrityError at commit
    because both tried to write version_number=1 for the same permit."""
    records = [
        _permit("DUP-1", description="first occurrence"),
        _permit("DUP-1", description="second occurrence, changed"),
    ]
    stats = _run(db_session, jurisdiction, records, monkeypatch)

    # Exactly one Permit row (the two occurrences collapse onto one permit).
    permits = db_session.query(Permit).filter(Permit.jurisdiction_id == jurisdiction.id).all()
    assert len(permits) == 1
    permit = permits[0]

    # Versions are sequential and gap-free (1, 2), no collision.
    versions = (
        db_session.query(PermitVersion)
        .filter(PermitVersion.permit_id == permit.id)
        .order_by(PermitVersion.version_number)
        .all()
    )
    assert [v.version_number for v in versions] == [1, 2]
    assert stats.fetched == 2
    assert stats.errors == 0


def test_duplicate_permit_number_in_one_batch_update_path(db_session, jurisdiction, monkeypatch):
    """Permit already exists (version 1 committed from a prior run), then a
    later batch contains the same permit_number TWICE with changing data.
    Pre-fix the second occurrence recomputed version_number=2 (identical to
    the first) and collided."""
    _run(db_session, jurisdiction, [_permit("REP-9", description="v1")], monkeypatch)

    records = [
        _permit("REP-9", description="v2 changed"),
        _permit("REP-9", description="v3 changed again"),
    ]
    stats = _run(db_session, jurisdiction, records, monkeypatch)

    permit = db_session.query(Permit).filter(Permit.jurisdiction_id == jurisdiction.id).one()
    versions = (
        db_session.query(PermitVersion)
        .filter(PermitVersion.permit_id == permit.id)
        .order_by(PermitVersion.version_number)
        .all()
    )
    assert [v.version_number for v in versions] == [1, 2, 3]
    assert stats.errors == 0


def test_many_duplicates_in_one_batch_do_not_collide(db_session, jurisdiction, monkeypatch):
    """Stress the path: the same permit_number ten times in one batch."""
    records = [_permit("MANY", description=f"occurrence {i}") for i in range(10)]
    # The key assertion: committing this batch must not raise IntegrityError.
    try:
        stats = _run(db_session, jurisdiction, records, monkeypatch)
    except IntegrityError:  # pragma: no cover - this is the bug we fixed
        pytest.fail("version-numbering collision regressed (IntegrityError on commit)")

    permit = db_session.query(Permit).filter(Permit.jurisdiction_id == jurisdiction.id).one()
    versions = [
        v.version_number
        for v in db_session.query(PermitVersion)
        .filter(PermitVersion.permit_id == permit.id)
        .order_by(PermitVersion.version_number)
        .all()
    ]
    # 1 created + 9 subsequent changed occurrences => versions 1..10, no gaps/dupes.
    assert versions == list(range(1, 11))
    assert len(versions) == len(set(versions))
    assert stats.errors == 0
