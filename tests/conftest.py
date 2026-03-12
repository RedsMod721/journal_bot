"""Shared pytest helpers.

Default validation targets the canonical ``src`` stack. Legacy ``app``-stack
tests are still available, but they are ignored unless
``INCLUDE_LEGACY_APP_TESTS=1`` is set in the environment.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest
from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = "sqlite:///:memory:"
_LEGACY_ENV_FLAG = "INCLUDE_LEGACY_APP_TESTS"
_LEGACY_IMPORT_MARKERS = (
    "from app.",
    "import app.",
    "app.main",
    "app.utils.database",
)


def _is_legacy_app_test(path: Path) -> bool:
    if path.suffix != ".py" or path.name == "conftest.py":
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False
    return any(marker in text for marker in _LEGACY_IMPORT_MARKERS)


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    if os.getenv(_LEGACY_ENV_FLAG) == "1":
        return False
    return _is_legacy_app_test(collection_path)


def _legacy_base():
    from app.utils.database import Base
    from app.models.user import User  # noqa: F401
    from app.models.theme import Theme  # noqa: F401
    from app.models.skill import Skill  # noqa: F401
    from app.models.title import TitleTemplate, UserTitle  # noqa: F401
    import app.models.mission_quest  # noqa: F401
    from app.models.journal_entry import JournalEntry  # noqa: F401
    from app.models.user_stats import UserStats  # noqa: F401
    from app.models.event_log import EventLog  # noqa: F401
    from app.models.item import ItemTemplate, UserItem  # noqa: F401

    return Base


@pytest.fixture(scope="function")
def db_engine():
    """Create a fresh in-memory engine for legacy ``app`` tests."""
    Base = _legacy_base()
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(db_engine) -> Generator[Session, None, None]:
    """Create a database session for each legacy ``app`` test."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fake() -> Faker:
    """Faker instance for generating realistic test data."""
    return Faker()


@pytest.fixture
def sample_user(db_session, fake):
    """Create a persisted sample user for legacy ``app`` tests."""
    from app.models.user import User

    user = User(username=fake.user_name(), email=fake.email())
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sample_theme(db_session, sample_user):
    """Create a persisted sample theme for legacy ``app`` tests."""
    from app.models.theme import Theme

    theme = Theme(
        user_id=sample_user.id,
        name="Education",
        description="Learning and growing",
    )
    db_session.add(theme)
    db_session.commit()
    db_session.refresh(theme)
    return theme


@pytest.fixture
def sample_skill(db_session, sample_user, sample_theme):
    """Create a persisted sample skill for legacy ``app`` tests."""
    from app.models.skill import Skill

    skill = Skill(
        user_id=sample_user.id,
        theme_id=sample_theme.id,
        name="Python Programming",
        description="Learn Python",
    )
    db_session.add(skill)
    db_session.commit()
    db_session.refresh(skill)
    return skill
