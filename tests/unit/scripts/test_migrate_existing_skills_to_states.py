"""Tests for migrate_existing_skills_to_states script helpers."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill
from src.db.models.user import User
from src.db.models.user_skill_state import UserSkillState
from src.scripts.migrate_existing_skills_to_states import migrate_user_skills

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


def test_migrate_user_skills_maps_global_id_to_hierarchy_source_id(db_session: Session):
    user = User(
        id="30000000-0000-0000-0000-000000000001",
        username="migrate_user",
        email="migrate@example.com",
        password_hash="hash",
        home_country="US",
    )
    db_session.add(user)

    global_skill = GlobalSkill(
        id="30000000-0000-0000-0000-000000000002",
        source_skill_id="skill_professional_programming",
        canonical_name="Programming",
        hierarchy_level=2,
        parent_skill_ids_json='["skill_professional_professional_growth"]',
    )
    db_session.add(global_skill)
    db_session.flush()

    db_session.add(
        Skill(
            id="30000000-0000-0000-0000-000000000003",
            user_id=user.id,
            name="Programming",
            canonical_name="programming",
            global_skill_id=global_skill.id,
            xp=250,
            level=3,
        )
    )
    db_session.commit()

    hierarchy = {
        "skill_professional_programming": {
            "canonical_name": "Programming",
            "hierarchy_level": 2,
            "parent_skill_ids": ["skill_professional_professional_growth"],
        }
    }

    inserted = migrate_user_skills(db_session, user.id, hierarchy)

    assert inserted == 1
    row = (
        db_session.query(UserSkillState)
        .filter(
            UserSkillState.user_id == user.id,
            UserSkillState.skill_id == global_skill.id,
        )
        .one()
    )
    assert row.state == "activated"
    assert row.activated_at is not None


def test_migrate_user_skills_is_idempotent(db_session: Session):
    user = User(
        id="30000000-0000-0000-0000-000000000011",
        username="migrate_user_idempotent",
        email="migrate-idempotent@example.com",
        password_hash="hash",
        home_country="US",
    )
    db_session.add(user)

    global_skill = GlobalSkill(
        id="30000000-0000-0000-0000-000000000012",
        source_skill_id="skill_mental_focus",
        canonical_name="Focus",
        hierarchy_level=2,
        parent_skill_ids_json='["skill_mental_mental_wellbeing"]',
    )
    db_session.add(global_skill)
    db_session.flush()

    db_session.add(
        Skill(
            id="30000000-0000-0000-0000-000000000013",
            user_id=user.id,
            name="Focus",
            canonical_name="focus",
            global_skill_id=global_skill.id,
            xp=0,
            level=1,
        )
    )
    db_session.commit()

    hierarchy = {
        "skill_mental_focus": {
            "canonical_name": "Focus",
            "hierarchy_level": 2,
            "parent_skill_ids": ["skill_mental_mental_wellbeing"],
        }
    }

    first = migrate_user_skills(db_session, user.id, hierarchy)
    second = migrate_user_skills(db_session, user.id, hierarchy)

    assert first == 1
    assert second == 0
    assert (
        db_session.query(UserSkillState)
        .filter(UserSkillState.user_id == user.id)
        .count()
        == 1
    )
