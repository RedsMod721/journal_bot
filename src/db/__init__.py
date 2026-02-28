"""
src.db — Database layer for the RPG Life Tracker.

Public surface:
    Base            — SQLAlchemy declarative base (src.db.base)
    engine          — configured engine, SQLite dev / PostgreSQL prod
    SessionLocal    — raw session factory (use get_db() in FastAPI instead)
    DATABASE_URL    — resolved DB URL (after YAML + env var priority chain)
    get_db          — FastAPI generator dependency (commit on success, rollback on error)
    db_session      — context-manager variant for scripts and tests
    init_db         — create all tables (idempotent, dev/test only)
    drop_db         — drop all tables (test teardown only)
    check_connection — ping the database; returns bool

Models are available via src.db.models.
"""
from src.db.base import Base
from src.db.session import (
    DATABASE_URL,
    SessionLocal,
    check_connection,
    db_session,
    drop_db,
    engine,
    get_db,
    init_db,
)

__all__ = [
    "Base",
    "DATABASE_URL",
    "engine",
    "SessionLocal",
    "get_db",
    "db_session",
    "init_db",
    "drop_db",
    "check_connection",
]
