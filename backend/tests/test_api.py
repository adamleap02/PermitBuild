from __future__ import annotations

from datetime import datetime, timezone

from app.models import Jurisdiction, Permit, SourceSystem


def _make_jurisdiction(db_session, name="APITown", state="TX"):
    j = Jurisdiction(
        name=name,
        state=state,
        level="city",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "example.data.socrata.com", "dataset_id": "abcd-1234", "mapping": "sf_building_permits"},
    )
    db_session.add(j)
    db_session.commit()
    db_session.refresh(j)
    return j


def _make_permit(db_session, jurisdiction, **overrides):
    defaults = dict(
        jurisdiction_id=jurisdiction.id,
        permit_number="A-100",
        permit_type="Remodel",
        status="issued",
        estimated_cost=25000.0,
        property_address="1 Test St",
        issue_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        description="kitchen remodel",
    )
    defaults.update(overrides)
    permit = Permit(**defaults)
    db_session.add(permit)
    db_session.commit()
    db_session.refresh(permit)
    return permit


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_and_list_jurisdictions(client):
    resp = client.post(
        "/jurisdictions",
        json={
            "name": "Sampleburg",
            "state": "CA",
            "source_system": "socrata",
            "source_config": {"domain": "data.example.gov", "dataset_id": "xyz-123"},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Sampleburg"
    assert body["source_system"] == "socrata"

    list_resp = client.get("/jurisdictions")
    assert list_resp.status_code == 200
    assert any(j["name"] == "Sampleburg" for j in list_resp.json())


def test_permit_search_and_filters(client, db_session):
    j = _make_jurisdiction(db_session)
    _make_permit(db_session, j, permit_number="A-100", estimated_cost=25000.0, description="kitchen remodel")
    _make_permit(db_session, j, permit_number="A-101", estimated_cost=800000.0, description="new construction custom home")

    resp = client.get("/permits", params={"jurisdiction_id": j.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2

    resp = client.get("/permits", params={"min_value": 100000})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["permit_number"] == "A-101"

    resp = client.get("/permits", params={"keyword": "kitchen"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["permit_number"] == "A-100"


def test_permit_map_returns_geocoded_points_with_counts(client, db_session):
    j = _make_jurisdiction(db_session, name="MapTown", state="TX")
    _make_permit(db_session, j, permit_number="M-1", latitude=30.1, longitude=-97.1)
    _make_permit(db_session, j, permit_number="M-2", latitude=30.2, longitude=-97.2)
    _make_permit(db_session, j, permit_number="M-3", latitude=None, longitude=None)  # ungeocoded

    resp = client.get("/permits/map", params={"jurisdiction_id": j.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_matching"] == 3
    assert body["total_geocoded"] == 2
    assert body["returned"] == 2
    assert len(body["items"]) == 2
    assert all(item["latitude"] is not None for item in body["items"])

    resp = client.get("/permits/map", params={"jurisdiction_id": j.id, "limit": 1})
    body = resp.json()
    assert body["returned"] == 1
    assert body["total_geocoded"] == 2  # count reflects all matches, not just the capped page


def test_permit_detail_includes_versions_and_score(client, db_session):
    j = _make_jurisdiction(db_session, name="DetailTown", state="NY")
    permit = _make_permit(db_session, j, permit_number="D-1")

    from app.models import PermitVersion, Score

    db_session.add(
        PermitVersion(permit_id=permit.id, version_number=1, snapshot={"status": "issued"}, changed_fields={})
    )
    db_session.add(
        Score(
            permit_id=permit.id,
            project_size_score=10.0,
            project_size_explanation="x",
            budget_tier="small",
            budget_tier_explanation="x",
            urgency_score=0.0,
            urgency_explanation="x",
            luxury_likelihood=0.0,
            luxury_explanation="x",
            remodel_vs_repair="remodel",
            remodel_vs_repair_explanation="x",
            investment_property_likelihood=0.0,
            investment_property_explanation="x",
            lead_score=12.3,
            lead_score_explanation="x",
            confidence_score=80.0,
            confidence_explanation="x",
        )
    )
    db_session.commit()

    resp = client.get(f"/permits/{permit.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["permit_number"] == "D-1"
    assert len(body["versions"]) == 1
    assert body["latest_score"]["lead_score"] == 12.3


def test_permit_detail_404_for_missing(client):
    resp = client.get("/permits/999999")
    assert resp.status_code == 404


def test_property_detail(client, db_session):
    from app.models import Property

    prop = Property(address="55 Elm St", normalized_address="55 ELM ST", latitude=1.1, longitude=2.2)
    db_session.add(prop)
    db_session.commit()
    db_session.refresh(prop)

    resp = client.get(f"/properties/{prop.id}")
    assert resp.status_code == 200
    assert resp.json()["address"] == "55 Elm St"


def test_export_csv(client, db_session):
    j = _make_jurisdiction(db_session, name="ExportTown", state="WA")
    _make_permit(db_session, j, permit_number="E-1")

    resp = client.get("/export", params={"jurisdiction_id": j.id})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "E-1" in resp.text
    assert "permit_number" in resp.text.splitlines()[0]


def test_ingest_run_with_mocked_connector(client, db_session, monkeypatch):
    j = _make_jurisdiction(db_session, name="IngestTown", state="OR")

    from app.connectors.base import PermitConnector, ConnectorInfo
    import app.ingest as ingest_module

    class FakeConnector(PermitConnector):
        source_system = "socrata"

        def discover(self):
            return ConnectorInfo(source_system="socrata", identifier="fake", display_name="fake")

        def fetch_permits(self, since=None, limit=None):
            yield {
                **self.normalized_stub(),
                "permit_number": "FAKE-1",
                "permit_type": "Remodel",
                "estimated_cost": 5000.0,
                "property_address": None,
                "source": "fake:test",
                "raw_data": {"permit_number": "FAKE-1"},
            }

    monkeypatch.setattr(ingest_module, "build_connector", lambda jurisdiction: FakeConnector())

    resp = client.post("/ingest/run", json={"jurisdiction_id": j.id, "limit": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["fetched"] == 1
    assert body["created"] == 1
    assert body["scored"] == 1

    permits_resp = client.get("/permits", params={"jurisdiction_id": j.id})
    assert permits_resp.json()["total"] == 1


def test_ingest_run_missing_jurisdiction_404(client):
    resp = client.post("/ingest/run", json={"jurisdiction_id": 999999})
    assert resp.status_code == 404
