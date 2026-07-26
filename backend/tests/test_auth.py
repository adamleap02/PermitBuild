from __future__ import annotations

from app.security import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_password_and_verify_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_hash_password_handles_long_input_without_error():
    long_password = "x" * 200
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed)


def test_create_and_decode_access_token():
    token = create_access_token(user_id=42)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert "exp" in payload


def test_signup_creates_org_and_user_and_returns_token(client):
    resp = client.post(
        "/auth/signup",
        json={
            "email": "founder@example.com",
            "password": "supersecret123",
            "full_name": "Founder Person",
            "organization_name": "Acme Construction Intel",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == "founder@example.com"
    assert body["user"]["organization_id"] > 0


def test_signup_duplicate_email_rejected(client):
    payload = {
        "email": "dupe@example.com",
        "password": "supersecret123",
        "organization_name": "DupeCo",
    }
    first = client.post("/auth/signup", json=payload)
    assert first.status_code == 201
    second = client.post("/auth/signup", json=payload)
    assert second.status_code == 409


def test_login_success_and_failure(client):
    client.post(
        "/auth/signup",
        json={"email": "loginuser@example.com", "password": "mypassword1", "organization_name": "LoginCo"},
    )

    good = client.post("/auth/login", json={"email": "loginuser@example.com", "password": "mypassword1"})
    assert good.status_code == 200
    assert good.json()["access_token"]

    bad = client.post("/auth/login", json={"email": "loginuser@example.com", "password": "wrongpassword"})
    assert bad.status_code == 401

    nonexistent = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert nonexistent.status_code == 401


def test_me_requires_auth_and_returns_current_user(client):
    unauth = client.get("/auth/me")
    assert unauth.status_code == 401

    signup_resp = client.post(
        "/auth/signup",
        json={"email": "meuser@example.com", "password": "mypassword1", "organization_name": "MeCo"},
    )
    token = signup_resp.json()["access_token"]

    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "meuser@example.com"


def test_me_rejects_garbage_token(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
