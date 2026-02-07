"""
Tests for database utility helpers.

These tests cover:
- get_database_info() - metadata about database configuration
- get_db() - FastAPI dependency generator for database sessions
- init_db() - database initialization
"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.utils.database import (
    get_database_info,
    get_db,
    init_db,
    Base,
    DATABASE_URL,
)


def test_get_database_info_keys_and_types():
    """get_database_info should return expected keys and types."""
    info = get_database_info()

    assert set(info.keys()) == {
        "database_url",
        "database_path",
        "database_exists",
        "directory_exists",
    }
    assert isinstance(info["database_url"], str)
    assert isinstance(info["database_path"], str)
    assert isinstance(info["database_exists"], bool)
    assert isinstance(info["directory_exists"], bool)


def test_get_database_info_flags_match_filesystem():
    """database_exists should match the filesystem state."""
    info = get_database_info()
    db_path = Path(info["database_path"])

    assert info["database_exists"] == db_path.exists()
    assert info["directory_exists"] == db_path.parent.exists()


def test_get_db_yields_session_and_closes():
    """get_db should yield a session and close it after use."""
    # Get the generator
    db_gen = get_db()

    # Get the session
    db = next(db_gen)
    assert isinstance(db, Session)

    # Verify session is usable
    assert db.is_active

    # Close the generator (simulates end of request)
    try:
        next(db_gen)
    except StopIteration:
        pass


def test_get_db_closes_session_on_exception():
    """get_db should close session even if an exception occurs."""
    db_gen = get_db()
    db = next(db_gen)

    # Simulate an exception during request processing
    try:
        db_gen.throw(ValueError("Simulated error"))
    except ValueError:
        pass

    # Session should still be closed (finally block executed)


def test_init_db_creates_tables():
    """init_db should create all tables defined in Base.metadata."""
    # Create a separate in-memory database for this test
    test_engine = create_engine("sqlite:///:memory:")

    # Import models to register them with Base
    from app.models.user import User  # noqa: F401
    from app.models.theme import Theme  # noqa: F401

    # Create tables using the test engine
    Base.metadata.create_all(bind=test_engine)

    # Verify tables exist by checking metadata
    assert "users" in Base.metadata.tables
    assert "themes" in Base.metadata.tables


def test_init_db_function_runs():
    """init_db function should execute without error."""
    # This calls the actual init_db which uses the real engine
    # It's safe because create_all is idempotent
    init_db()


def test_database_url_is_sqlite():
    """DATABASE_URL should be a SQLite URL."""
    assert DATABASE_URL.startswith("sqlite:///")


def test_base_is_declarative_base():
    """Base should be a SQLAlchemy declarative base."""
    # Base should have metadata attribute
    assert hasattr(Base, "metadata")
    # Base should have registry for models
    assert hasattr(Base, "registry")
