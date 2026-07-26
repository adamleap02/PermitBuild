from __future__ import annotations

from app import billing


def test_billing_not_configured_without_stripe_key():
    assert billing.is_configured() is False


def test_billing_status_reports_not_configured(client, auth_headers):
    resp = client.get("/billing/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert "BLOCKERS.md" in body["message"]


def test_billing_status_requires_auth(client):
    resp = client.get("/billing/status")
    assert resp.status_code == 401


def test_checkout_session_returns_503_when_not_configured(client, auth_headers):
    resp = client.post(
        "/billing/checkout-session",
        json={"plan": "pro"},
        headers=auth_headers,
    )
    assert resp.status_code == 503
    assert "STRIPE_SECRET_KEY" in resp.json()["detail"]


def test_webhook_returns_503_when_not_configured(client):
    resp = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "fake"})
    assert resp.status_code == 503


def test_billing_operations_raise_not_configured_error_directly():
    import pytest

    with pytest.raises(billing.BillingNotConfiguredError):
        billing.get_or_create_customer(1, "Test Org", "test@example.com")

    with pytest.raises(billing.BillingNotConfiguredError):
        billing.create_checkout_session("cus_fake", "pro", "http://x/success", "http://x/cancel")
