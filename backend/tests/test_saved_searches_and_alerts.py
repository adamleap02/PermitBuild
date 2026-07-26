from __future__ import annotations

from datetime import datetime, timezone

from app.models import AlertNotificationLog, Jurisdiction, Permit, SourceSystem


def _make_jurisdiction(db_session, name="AlertTown", state="TX"):
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


def _make_permit(db_session, jurisdiction, **overrides):
    defaults = dict(
        jurisdiction_id=jurisdiction.id,
        permit_number="AL-1",
        permit_type="Remodel",
        estimated_cost=50000.0,
        property_address="1 Alert St",
        issue_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        description="kitchen remodel",
    )
    defaults.update(overrides)
    permit = Permit(**defaults)
    db_session.add(permit)
    db_session.commit()
    db_session.refresh(permit)
    return permit


def test_create_list_delete_saved_search(client, auth_headers):
    create_resp = client.post(
        "/saved-searches",
        json={"name": "Big Remodels", "filters": {"keyword": "remodel", "min_value": 10000}},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    saved = create_resp.json()
    assert saved["name"] == "Big Remodels"
    assert saved["filters"]["min_value"] == 10000

    list_resp = client.get("/saved-searches", headers=auth_headers)
    assert list_resp.status_code == 200
    assert any(s["id"] == saved["id"] for s in list_resp.json())

    get_resp = client.get(f"/saved-searches/{saved['id']}", headers=auth_headers)
    assert get_resp.status_code == 200

    delete_resp = client.delete(f"/saved-searches/{saved['id']}", headers=auth_headers)
    assert delete_resp.status_code == 204

    missing_resp = client.get(f"/saved-searches/{saved['id']}", headers=auth_headers)
    assert missing_resp.status_code == 404


def test_saved_search_requires_auth(client):
    resp = client.post("/saved-searches", json={"name": "x", "filters": {}})
    assert resp.status_code == 401


def test_saved_search_isolated_per_organization(client):
    # Org A creates a saved search
    org_a = client.post(
        "/auth/signup", json={"email": "a@example.com", "password": "password123", "organization_name": "Org A"}
    ).json()
    headers_a = {"Authorization": f"Bearer {org_a['access_token']}"}
    saved = client.post(
        "/saved-searches", json={"name": "Org A Search", "filters": {}}, headers=headers_a
    ).json()

    # Org B should not be able to see or delete it
    org_b = client.post(
        "/auth/signup", json={"email": "b@example.com", "password": "password123", "organization_name": "Org B"}
    ).json()
    headers_b = {"Authorization": f"Bearer {org_b['access_token']}"}

    get_as_b = client.get(f"/saved-searches/{saved['id']}", headers=headers_b)
    assert get_as_b.status_code == 404


def test_create_and_run_alert_delivers_stub_and_logs(client, auth_headers, db_session):
    jurisdiction = _make_jurisdiction(db_session)
    _make_permit(db_session, jurisdiction, permit_number="AL-100", description="kitchen remodel")

    saved_search_resp = client.post(
        "/saved-searches",
        json={"name": "Remodels", "filters": {"keyword": "remodel"}},
        headers=auth_headers,
    )
    saved_search_id = saved_search_resp.json()["id"]

    alert_resp = client.post(
        "/alerts",
        json={
            "saved_search_id": saved_search_id,
            "channel": "email",
            "recipient": "leads@example.com",
            "frequency": "daily",
        },
        headers=auth_headers,
    )
    assert alert_resp.status_code == 201
    alert = alert_resp.json()
    assert alert["channel"] == "email"
    assert alert["last_checked_at"] is None

    list_resp = client.get("/alerts", headers=auth_headers)
    assert any(a["id"] == alert["id"] for a in list_resp.json())

    run_resp = client.post(f"/alerts/{alert['id']}/run", headers=auth_headers)
    assert run_resp.status_code == 200
    run_body = run_resp.json()
    assert run_body["matched_permits"] == 1
    assert run_body["delivery_status"] == "stubbed"
    assert run_body["delivery_log_id"] is not None

    log = db_session.query(AlertNotificationLog).filter(AlertNotificationLog.id == run_body["delivery_log_id"]).one()
    assert log.status == "stubbed"
    assert log.recipient == "leads@example.com"
    assert "AL-100" in log.body

    delete_resp = client.delete(f"/alerts/{alert['id']}", headers=auth_headers)
    assert delete_resp.status_code == 204


def test_create_alert_for_nonexistent_saved_search_404(client, auth_headers):
    resp = client.post(
        "/alerts",
        json={"saved_search_id": 999999, "channel": "email", "recipient": "x@example.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_create_alert_invalid_channel_422(client, auth_headers):
    saved_search_resp = client.post(
        "/saved-searches", json={"name": "X", "filters": {}}, headers=auth_headers
    )
    saved_search_id = saved_search_resp.json()["id"]

    resp = client.post(
        "/alerts",
        json={"saved_search_id": saved_search_id, "channel": "carrier-pigeon", "recipient": "x@example.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
