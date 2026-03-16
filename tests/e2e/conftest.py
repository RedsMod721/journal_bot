"""
Shared fixtures for E2E pipeline tests.

All tests run against an in-memory SQLite database with FK enforcement OFF.
SessionLocal is monkey-patched into src.db.base so every pipeline step that does
``from src.db.base import SessionLocal`` resolves to the test session factory
rather than the production engine.

Why patch src.db.base instead of src.db.session?
    The pipeline steps (5, 8–15) import SessionLocal with the pattern
        from src.db.base import SessionLocal
    which looks up the name directly in the src.db.base module dict.
    Patching that dict ensures the lookup succeeds without modifying
    any production code.
"""
from __future__ import annotations

import uuid
from typing import Generator

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.base as _base_module
import src.db.models  # noqa: F401  — register all ORM mappers
from src.db.base import Base
from src.db.models.user import User
from src.ai.pipeline.entry_pipeline import EntryPipeline


# ---------------------------------------------------------------------------
# Engine / session helpers
# ---------------------------------------------------------------------------


def _make_test_engine():
    """In-memory SQLite engine with FK enforcement OFF for isolated E2E tests."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(eng, "connect")
    def _disable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys = OFF")

    Base.metadata.create_all(bind=eng)
    return eng


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def engine():
    eng = _make_test_engine()
    yield eng
    eng.dispose()


@pytest.fixture(scope="function")
def session_factory(engine):
    """Raw sessionmaker bound to the test engine."""
    return sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest.fixture(scope="function")
def db(session_factory) -> Generator[Session, None, None]:
    """Single session for the lifetime of a test."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def test_user(db: Session) -> User:
    """Persisted User row for the test database."""
    u = User(
        id=str(uuid.uuid4()),
        username="e2e_pipeline_user",
        email="e2e_pipeline@test.example",
        password_hash="not-used",
        home_country="US",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture(scope="function", autouse=True)
def patch_session_local(session_factory):
    """
    Inject SessionLocal into src.db.base so pipeline steps that do
    ``from src.db.base import SessionLocal`` use the test DB.

    The test session_factory is a SQLAlchemy sessionmaker instance whose
    __call__() returns a Session.  Session supports the context-manager
    protocol (``with session_factory() as db:``), so no wrapper class is
    needed.
    """
    _sentinel = object()
    original = getattr(_base_module, "SessionLocal", _sentinel)
    _base_module.SessionLocal = session_factory
    yield
    if original is _sentinel:
        try:
            delattr(_base_module, "SessionLocal")
        except AttributeError:
            pass
    else:
        _base_module.SessionLocal = original


@pytest.fixture(scope="function")
def pipeline(db: Session) -> EntryPipeline:
    """EntryPipeline wired to the test session (no AI services)."""
    return EntryPipeline(db=db)
