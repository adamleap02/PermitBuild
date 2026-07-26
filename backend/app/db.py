"""
Database engine/session setup.

Defaults to a local SQLite file at backend/data/local.db so the whole
stack runs with zero external services. Point DATABASE_URL at a
Postgres instance (e.g. postgresql+psycopg://user:pass@host/db) later
and every model / query in this codebase keeps working unchanged --
see app/models.py for notes on the Postgres/PostGIS upgrade path.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load backend/.env (gitignored -- never commit real values) into the
# process environment, WITHOUT overriding anything already set (e.g. by
# the shell, docker-compose, or tests/conftest.py's explicit test
# isolation). app/db.py is imported transitively by nearly every other
# module in this codebase, so this is the earliest safe, dependency-free
# place to do it -- every module that reads os.environ.get(...) for a
# key/secret at import time (app/billing.py, app/security.py,
# app/enrichment/census_acs.py) needs this to have already run.
load_dotenv(BACKEND_DIR / ".env", override=False)

DEFAULT_SQLITE_URL = f"sqlite:///{(DATA_DIR / 'local.db').as_posix()}"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)

IS_SQLITE = DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False} if IS_SQLITE else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)

if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        # Enforce FK constraints (off by default in SQLite) and use WAL
        # for better concurrent read/write behavior during ingest runs.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    """FastAPI dependency that yields a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
