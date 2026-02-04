"""
Global pytest fixtures for Status Window API tests.

This module provides shared fixtures used across all test modules:
- Database fixtures (in-memory SQLite for fast, isolated tests)
- Test data generators (Faker)
- Sample model instances (User, Theme, Skill)

Usage:
    def test_something(db_session, fake, sample_user):
        # db_session: SQLAlchemy session for database operations
        # fake: Faker instance for generating test data
        # sample_user: Pre-created user instance
        ...
"""
import pytest
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.utils.database import Base
from faker import Faker

# Import all models to ensure SQLAlchemy registers them with Base.metadata
# This is necessary for create_all() to create all tables with proper foreign keys
from app.models.user import User  # noqa: F401
from app.models.theme import Theme  # noqa: F401
from app.models.skill import Skill  # noqa: F401
from app.models.title import TitleTemplate, UserTitle  # noqa: F401


# Use in-memory SQLite for tests (fast, isolated, no cleanup needed)
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_engine():
    """
    Create a fresh database engine for each test.

    Uses in-memory SQLite for speed. Creates all tables before the test
    and drops them after, ensuring complete isolation between tests.

    Yields:
        Engine: SQLAlchemy engine connected to in-memory database
    """
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """
    Create a database session for each test.

    Provides a fresh session connected to the test database engine.
    Session is automatically closed after the test completes.

    Args:
        db_engine: The database engine fixture

    Yields:
        Session: SQLAlchemy session for database operations
    """
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_engine
    )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fake() -> Faker:
    """
    Faker instance for generating realistic test data.

    Provides consistent fake data generation across tests.
    Use for generating usernames, emails, text, dates, etc.

    Returns:
        Faker: Configured Faker instance

    Example:
        def test_user_creation(fake):
            username = fake.user_name()
            email = fake.email()
            bio = fake.text(max_nb_chars=200)
    """
    return Faker()


# =============================================================================
# MODEL FIXTURES
# =============================================================================

@pytest.fixture
def sample_user(db_session, fake):
    """
    Create a sample user for testing.

    Provides a persisted User instance with realistic fake data.
    Useful as a dependency for fixtures that require a user (themes, skills, etc.)

    Args:
        db_session: Database session fixture
        fake: Faker instance fixture

    Returns:
        User: A persisted User instance
    """
    from app.models.user import User

    user = User(
        username=fake.user_name(),
        email=fake.email()
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sample_theme(db_session, sample_user):
    """
    Create a sample theme for testing.

    Provides a persisted Theme instance linked to a sample user.
    Useful for testing theme-related functionality and as a dependency
    for skill fixtures.

    Args:
        db_session: Database session fixture
        sample_user: Sample user fixture

    Returns:
        Theme: A persisted Theme instance
    """
    from app.models.theme import Theme

    theme = Theme(
        user_id=sample_user.id,
        name="Education",
        description="Learning and growing"
    )
    db_session.add(theme)
    db_session.commit()
    db_session.refresh(theme)
    return theme


@pytest.fixture
def sample_skill(db_session, sample_user, sample_theme):
    """
    Create a sample skill for testing.

    Provides a persisted Skill instance linked to a sample user and theme.
    Useful for testing skill-related functionality including XP and leveling.

    Args:
        db_session: Database session fixture
        sample_user: Sample user fixture
        sample_theme: Sample theme fixture

    Returns:
        Skill: A persisted Skill instance
    """
    from app.models.skill import Skill

    skill = Skill(
        user_id=sample_user.id,
        theme_id=sample_theme.id,
        name="Python Programming",
        description="Learn Python"
    )
    db_session.add(skill)
    db_session.commit()
    db_session.refresh(skill)
    return skill
