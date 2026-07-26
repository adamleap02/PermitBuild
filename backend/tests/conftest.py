"""
Test configuration. Points the app at an isolated, throwaway SQLite
file (never the real backend/data/local.db) BEFORE any `app.*` module
is imported, then builds the schema directly from the SQLAlchemy
models (bypassing Alembic -- fine for tests, which just need the
tables to exist).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_tmp_dir = tempfile.mkdtemp(prefix="construction_intel_test_")
_TEST_DB_PATH = Path(_tmp_dir) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-not-for-production"
# Explicitly unset so tests deterministically exercise the "billing not
# configured" degrade-gracefully path regardless of the host environment.
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ.pop("STRIPE_WEBHOOK_SECRET", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402  (imports app.db, which calls load_dotenv())

# app.db's import above loads backend/.env (if present) with override=False,
# which can populate secrets a developer has locally (e.g. CENSUS_API_KEY)
# into os.environ. Re-assert test isolation here, AFTER dotenv has had its
# chance to run but BEFORE any module that reads these at import time
# (app/enrichment/census_acs.py, app/billing.py) gets imported below --
# tests must behave the same on every machine regardless of a
# contributor's local .env contents.
os.environ.pop("STRIPE_SECRET_KEY", None)
os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
os.environ.pop("CENSUS_API_KEY", None)

from app import models  # noqa: E402  (register all tables on Base.metadata)
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        # Clean up all rows between tests so each test starts fresh
        # without needing to recreate the schema every time.
        session.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()


@pytest.fixture()
def client(db_session):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    """Signs up a fresh user/org and returns Authorization headers for it."""
    resp = client.post(
        "/auth/signup",
        json={
            "email": "fixture-user@example.com",
            "password": "fixturepassword1",
            "organization_name": "Fixture Org",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
