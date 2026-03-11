"""Tests for theme/mapping backfill script helpers."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.scripts.backfill_themes_and_mappings import backfill_user
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill, SkillThemeMapping, Theme
from src.db.models.user import User

pytestmark = [pytest.mark.unit]


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_backfill_user_repairs_missing_themes_and_mappings(db_session: Session):
    user = User(
        id="20000000-0000-0000-0000-000000000001",
        username="backfill_user",
        email="backfill@example.com",
        password_hash="hash",
        home_country="US",
    )
    db_session.add(user)

    global_skill = GlobalSkill(
        id="20000000-0000-0000-0000-000000000002",
        source_skill_id="skill_professional_programming",
        canonical_name="Programming",
        related_themes_json='["Professional", "Mental"]',
    )
    db_session.add(global_skill)
    db_session.flush()

    user_skill = Skill(
        id="20000000-0000-0000-0000-000000000003",
        user_id=user.id,
        name="Programming",
        canonical_name="programming",
        global_skill_id=global_skill.id,
    )
    db_session.add(user_skill)
    db_session.commit()

    result = backfill_user(db_session, user.id)
    db_session.commit()

    assert result.user_id == user.id
    assert result.themes_created == 12
    assert result.mappings_created == 2
    assert result.skill_count == 1
    assert db_session.query(Theme).filter(Theme.user_id == user.id).count() == 12
    assert (
        db_session.query(SkillThemeMapping)
        .filter(SkillThemeMapping.user_id == user.id)
        .count()
        == 2
    )


def test_backfill_user_is_idempotent(db_session: Session):
    user = User(
        id="20000000-0000-0000-0000-000000000011",
        username="backfill_idempotent",
        email="backfill-idempotent@example.com",
        password_hash="hash",
        home_country="US",
    )
    db_session.add(user)
    db_session.commit()

    first = backfill_user(db_session, user.id)
    db_session.commit()
    second = backfill_user(db_session, user.id)
    db_session.commit()

    assert first.themes_created == 12
    assert second.themes_created == 0
    assert first.mappings_created == 0
    assert second.mappings_created == 0
    assert db_session.query(Theme).filter(Theme.user_id == user.id).count() == 12
