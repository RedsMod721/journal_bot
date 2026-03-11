"""Unit tests for Step 13 theme award persistence behavior."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai.steps.rewards import persist_theme_awards
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.global_kb import GlobalSkill
from src.db.models.journal_entry import JournalEntry
from src.db.models.quest import Quest
from src.db.models.skill import Skill
from src.db.models.user import User
from src.db.models.xp import XpAward

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


def test_persist_theme_awards_applies_full_point_one_percent_per_mapped_theme(
    db_session: Session,
):
    user = User(
        id="10000000-0000-0000-0000-000000000001",
        username="theme_award_user",
        email="theme-award@example.com",
        password_hash="hash",
        home_country="US",
    )
    db_session.add(user)

    global_skill = GlobalSkill(
        id="10000000-0000-0000-0000-000000000002",
        source_skill_id="skill_professional_programming",
        canonical_name="Programming",
        related_themes_json='["Professional", "Mental", "Intellectual"]',
    )
    db_session.add(global_skill)
    db_session.flush()

    skill = Skill(
        id="10000000-0000-0000-0000-000000000003",
        user_id=user.id,
        name="Programming",
        canonical_name="programming",
        global_skill_id=global_skill.id,
    )
    db_session.add(skill)

    entry = JournalEntry(
        id="10000000-0000-0000-0000-000000000004",
        user_id=user.id,
        content="I worked on programming tasks.",
        entry_type="text",
        status="completed",
    )
    db_session.add(entry)

    quest = Quest(
        id="10000000-0000-0000-0000-000000000005",
        user_id=user.id,
        skill_id=skill.id,
        name="Ship feature",
        quest_type="instant",
        completion_type="one_time",
        base_xp=480,
        status="active",
        required_progress=1,
        current_progress=1,
    )
    db_session.add(quest)
    db_session.commit()

    skill_awards = [
        {
            "award_id": "10000000-0000-0000-0000-000000000006",
            "skill_id": skill.id,
            "quest_id": quest.id,
            "amount": 5000,
            "identity_key": "skill-key",
            "replayed": False,
        }
    ]

    result = persist_theme_awards(
        user_id=user.id,
        entry_id=entry.id,
        processing_run_id="10000000-0000-0000-0000-000000000007",
        skill_awards=skill_awards,
        db=db_session,
        pipeline_version="week4-v1",
        ruleset_version="s10-v8",
    )
    db_session.commit()

    assert len(result["theme_awards"]) == 3
    assert all(row["amount"] == 50 for row in result["theme_awards"])

    persisted = (
        db_session.query(XpAward)
        .filter(XpAward.user_id == user.id, XpAward.theme_id.isnot(None))
        .all()
    )
    assert len(persisted) == 3
    assert all(row.amount == 50 for row in persisted)
    assert all(row.source_skill_id == skill.id for row in persisted)
    assert all(row.source_skill_xp == 5000 for row in persisted)

    # Replay/idempotency: no new rows, marked replayed.
    replay = persist_theme_awards(
        user_id=user.id,
        entry_id=entry.id,
        processing_run_id="10000000-0000-0000-0000-000000000008",
        skill_awards=skill_awards,
        db=db_session,
        pipeline_version="week4-v1",
        ruleset_version="s10-v8",
    )
    db_session.commit()
    assert len(replay["theme_awards"]) == 3
    assert all(row["replayed"] for row in replay["theme_awards"])
    assert (
        db_session.query(XpAward)
        .filter(XpAward.user_id == user.id, XpAward.theme_id.isnot(None))
        .count()
        == 3
    )
