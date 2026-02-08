"""
Database configuration and utilities for Status Window API.

This module provides:
- SQLAlchemy engine configuration for SQLite
- Session factory for database connections
- FastAPI dependency for database sessions
- Base class for ORM models

Usage:
    from app.utils.database import Base, get_db, engine

    # In models:
    class User(Base):
        __tablename__ = "users"
        ...

    # In API endpoints:
    @app.get("/users")
    def get_users(db: Session = Depends(get_db)):
        return db.query(User).all()
"""
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Database file path - relative to project root
DATABASE_DIR = Path(__file__).parent.parent.parent / "data"
DATABASE_PATH = DATABASE_DIR / "database.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Ensure data directory exists
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

# Create SQLAlchemy engine
# check_same_thread=False is required for SQLite to work with FastAPI's
# multi-threaded environment. Each request may run in a different thread,
# but SQLite by default only allows access from the thread that created it.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,  # Set to True for SQL query logging during development
)

# SessionLocal factory for creating database sessions
# autocommit=False: We want explicit commits
# autoflush=False: We want explicit flushes for better control
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Base class for all ORM models
# All models should inherit from this class
class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Yields a database session that is automatically closed after the request
    completes, ensuring proper resource cleanup.

    Usage:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()

    Yields:
        Session: SQLAlchemy database session

    Note:
        The session is automatically closed in the finally block,
        even if an exception occurs during request processing.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize the database by creating all tables.

    This function creates all tables defined by models that inherit from Base.
    Should be called during application startup or when setting up a new database.

    Note:
        This does not handle migrations. For schema changes after initial
        creation, use Alembic migrations instead.
    """
    Base.metadata.create_all(bind=engine)


def get_database_info() -> dict:
    """
    Get information about the database configuration.

    Returns:
        dict: Database configuration details including path and connection status
    """
    return {
        "database_url": DATABASE_URL,
        "database_path": str(DATABASE_PATH),
        "database_exists": DATABASE_PATH.exists(),
        "directory_exists": DATABASE_DIR.exists(),
    }
