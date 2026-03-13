"""Regression tests for quest progress update helpers."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai.steps import quests
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.journal_entry import JournalEntry
from src.db.models.quest import Quest
from src.db.models.quest_progress import QuestProgress
from src.db.models.skill import Skill
from src.db.models.user import User


def _make_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return local()


def test_update_progress_initializes_missing_streak_progress_row() -> None:
    with _make_db() as db:
        user = User(
            id="00000000-0000-0000-0000-000000000301",
            email="quests-step@example.com",
            password_hash="x",
            home_country="US",
        )
        skill = Skill(
            id="00000000-0000-0000-0000-000000000302",
            user_id=user.id,
            name="Backend Development",
            canonical_name="backend development",
            level=1,
            rank="F",
            xp=0,
        )
        quest = Quest(
            id="00000000-0000-0000-0000-000000000303",
            user_id=user.id,
            skill_id=skill.id,
            name="Backend reliability streak",
            quest_type="longterm",
            completion_type="streak",
            base_xp=480,
            status="active",
            required_progress=7,
            current_progress=2,
        )
        entry = JournalEntry(
            id="00000000-0000-0000-0000-000000000304",
            user_id=user.id,
            content="I practiced backend development today for three focused hours.",
            entry_type="text",
            status="pending",
            question_state="none",
        )
        db.add_all([user, skill, quest, entry])
        db.commit()

        out = quests.update_progress(
            entry=entry,
            user_id=user.id,
            matched_quest_ids=[quest.id],
            db=db,
        )

        qp = (
            db.query(QuestProgress)
            .filter(
                QuestProgress.user_id == user.id,
                QuestProgress.quest_id == quest.id,
            )
            .one()
        )

        assert out["matched_quest_count"] == 1
        assert out["completed_quest_ids"] == []
        assert quest.current_progress == 3
        assert qp.progress_value == 3
        assert qp.streak_current == 3
        assert qp.streak_best == 3


def test_update_progress_normalizes_existing_null_like_counters() -> None:
    with _make_db() as db:
        user = User(
            id="00000000-0000-0000-0000-000000000311",
            email="quests-step-null@example.com",
            password_hash="x",
            home_country="US",
        )
        skill = Skill(
            id="00000000-0000-0000-0000-000000000312",
            user_id=user.id,
            name="Professional Growth",
            canonical_name="professional growth",
            level=1,
            rank="F",
            xp=0,
        )
        quest = Quest(
            id="00000000-0000-0000-0000-000000000313",
            user_id=user.id,
            skill_id=skill.id,
            name="Weekly review",
            quest_type="longterm",
            completion_type="recursive",
            base_xp=480,
            status="active",
            required_progress=3,
            current_progress=0,
        )
        entry = JournalEntry(
            id="00000000-0000-0000-0000-000000000314",
            user_id=user.id,
            content="I reviewed my professional growth goals.",
            entry_type="text",
            status="pending",
            question_state="none",
        )
        db.add_all([user, skill, quest, entry])
        db.commit()
        quest.current_progress = None

        out = quests.update_progress(
            entry=entry,
            user_id=user.id,
            matched_quest_ids=[quest.id],
            db=db,
        )

        qp = (
            db.query(QuestProgress)
            .filter(
                QuestProgress.user_id == user.id,
                QuestProgress.quest_id == quest.id,
            )
            .one()
        )

        assert out["matched_quest_count"] == 1
        assert quest.current_progress == 1
        assert qp.progress_value == 1
