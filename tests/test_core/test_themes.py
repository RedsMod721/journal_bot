"""Unit tests for canonical theme bootstrap and mapping helpers."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.themes import CANONICAL_THEME_NAMES, ensure_skill_theme_mappings, ensure_user_themes
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


@pytest.fixture
def user(db_session: Session) -> User:
    row = User(
        id="11111111-1111-1111-1111-111111111111",
        username="themes_user",
        email="themes@example.com",
        password_hash="hash",
        home_country="US",
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_ensure_user_themes_creates_exactly_12_canonical_rows(db_session: Session, user: User):
    themes_by_name = ensure_user_themes(db_session, user.id)
    db_session.commit()

    assert set(themes_by_name.keys()) == set(CANONICAL_THEME_NAMES)
    persisted = db_session.query(Theme).filter(Theme.user_id == user.id).all()
    assert len(persisted) == 12

    # Idempotent on rerun.
    themes_by_name_second = ensure_user_themes(db_session, user.id)
    db_session.commit()
    persisted_after = db_session.query(Theme).filter(Theme.user_id == user.id).all()
    assert len(persisted_after) == 12
    assert set(themes_by_name_second.keys()) == set(CANONICAL_THEME_NAMES)


def test_ensure_skill_theme_mappings_is_many_to_many_and_idempotent(
    db_session: Session,
    user: User,
):
    skill_1_global = GlobalSkill(
        id="00000000-0000-0000-0000-000000000101",
        source_skill_id="skill_professional_programming",
        canonical_name="Programming",
        related_themes_json='["Professional", "Mental", "Intellectual", "Nope"]',
    )
    skill_2_global = GlobalSkill(
        id="00000000-0000-0000-0000-000000000102",
        source_skill_id="skill_physical_running",
        canonical_name="Running",
        related_themes_json='["Physical", "Discipline", "  rest  ", ""]',
    )
    db_session.add_all([skill_1_global, skill_2_global])
    db_session.flush()

    user_skill_1 = Skill(
        id="00000000-0000-0000-0000-000000000201",
        user_id=user.id,
        name="Programming",
        canonical_name="programming",
        global_skill_id=skill_1_global.id,
    )
    user_skill_2 = Skill(
        id="00000000-0000-0000-0000-000000000202",
        user_id=user.id,
        name="Running",
        canonical_name="running",
        global_skill_id=skill_2_global.id,
    )
    db_session.add_all([user_skill_1, user_skill_2])
    db_session.flush()

    created = ensure_skill_theme_mappings(
        db_session,
        user.id,
        [user_skill_1.id, user_skill_2.id],
    )
    db_session.commit()
    assert created == 6

    mappings = (
        db_session.query(SkillThemeMapping)
        .filter(SkillThemeMapping.user_id == user.id)
        .all()
    )
    assert len(mappings) == 6

    themes_by_id = {
        row.id: row.name
        for row in db_session.query(Theme).filter(Theme.user_id == user.id).all()
    }
    skill_to_theme_names = {
        skill_id: sorted(
            themes_by_id[row.theme_id]
            for row in mappings
            if row.skill_id == skill_id
        )
        for skill_id in (user_skill_1.id, user_skill_2.id)
    }
    assert skill_to_theme_names[user_skill_1.id] == [
        "Intellectual",
        "Mental",
        "Professional",
    ]
    assert skill_to_theme_names[user_skill_2.id] == [
        "Discipline",
        "Physical",
        "Rest",
    ]

    # Invalid names were ignored and rerun does not duplicate mappings.
    created_again = ensure_skill_theme_mappings(
        db_session,
        user.id,
        [user_skill_1.id, user_skill_2.id],
    )
    db_session.commit()
    assert created_again == 0
    assert (
        db_session.query(SkillThemeMapping)
        .filter(SkillThemeMapping.user_id == user.id)
        .count()
        == 6
    )
