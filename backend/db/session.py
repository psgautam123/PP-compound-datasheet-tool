"""Engine/session factory.

Reads DATABASE_URL from the environment. Production target is Postgres
(e.g. postgresql+psycopg://user:pass@host/dbname) per the architecture
plan; this dev environment has no local Postgres/Docker available, so the
default falls back to a SQLite file so the app, seed script, and tests can
run without one. The schema (db/models.py) and Alembic migration are
written Postgres-first (JSONB variant, etc.) -- run against a real
Postgres instance by setting DATABASE_URL before `alembic upgrade head`.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH}"


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def make_engine(database_url: str | None = None):
    url = database_url or get_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


_engine = make_engine()
SessionLocal: sessionmaker[Session] = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Session:
    """FastAPI dependency: yields a session, closes it after the request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
