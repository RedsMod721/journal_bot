"""Week 3 pipeline contract tests."""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai.pipeline import PipelineProcessor
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.processing import EntryIdempotencyClaim, OutboxEvent, ProcessingJob
from src.db.models.quest import Quest
from src.db.models.skill import Skill, SkillThemeMapping, Theme
from src.db.models.user import User
from src.db.models.xp import XpAward


class _HealthyOllama:
    model = "llama3.2:3b"

    def health(self):
        return {
            "connected": True,
            "model_available": True,
            "models": ["llama3.2:3b"],
        }

    def embed(self, _text: str):
        return [0.01] * 384

    def generate_json(self, _prompt: str) -> dict:
        return {
            "response": '{"insight_text": "Great session!", "category": "skill_development", "confidence": 0.9}'
        }


class _DownOllama:
    model = "llama3.2:3b"

    def health(self):
        return {
            "connected": False,
            "model_available": False,
            "models": [],
            "error": "connection refused",
        }

    def embed(self, _text: str):  # pragma: no cover
        raise RuntimeError("should not be called when down")


class _HealthyQdrant:
    vector_size = 384
    collection = "rag_documents"

    def ensure_collection(self):
        return None

    def search(self, _vector, limit=5):
        return [{"point_id": "p1", "score": 0.91, "payload": {"title": "doc"}}][:limit]


class _DownQdrant:
    vector_size = 384
    collection = "rag_documents"

    def ensure_collection(self):
        raise RuntimeError("qdrant unavailable")

    def search(self, _vector, limit=5):  # pragma: no cover
        raise RuntimeError("should not be reached")


@dataclass
class _FixtureIds:
    user_id: str
    entry_id: str
    skill_id: str
    theme_id: str
    quest_id: str


def _make_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return session_local()


def _seed_core_graph(db: Session) -> _FixtureIds:
    user = User(
        id="00000000-0000-0000-0000-000000000101",
        email="week3@example.com",
        password_hash="x",
        home_country="US",
    )
    db.add(user)

    skill = Skill(
        id="00000000-0000-0000-0000-000000000102",
        user_id=user.id,
        name="Python Programming",
        canonical_name="python programming",
        level=1,
        rank="F",
        xp=0,
    )
    db.add(skill)

    theme = Theme(
        id="00000000-0000-0000-0000-000000000103",
        user_id=user.id,
        name="Professional",
        level=1,
        rank="F",
        xp=0,
    )
    db.add(theme)
    db.flush()

    db.add(
        SkillThemeMapping(
            id="00000000-0000-0000-0000-000000000104",
            user_id=user.id,
            skill_id=skill.id,
            theme_id=theme.id,
        )
    )

    quest = Quest(
        id="00000000-0000-0000-0000-000000000105",
        user_id=user.id,
        skill_id=skill.id,
        name="Ship Python quest",
        quest_type="instant",
        completion_type="one_time",
        base_xp=480,
        status="active",
        required_progress=1,
        current_progress=0,
    )
    db.add(quest)

    entry = JournalEntry(
        id="00000000-0000-0000-0000-000000000106",
        user_id=user.id,
        content="Today I did focused python programming and code review.",
        entry_type="text",
        status="pending",
        question_state="none",
    )
    db.add(entry)

    db.commit()

    return _FixtureIds(
        user_id=user.id,
        entry_id=entry.id,
        skill_id=skill.id,
        theme_id=theme.id,
        quest_id=quest.id,
    )


def test_pipeline_happy_path_persists_structured_and_awards():
    with _make_db() as db:
        ids = _seed_core_graph(db)

        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_HealthyQdrant()
        )
        result = processor.process_entry(
            entry_id=ids.entry_id,
            user_id=ids.user_id,
            idempotency_key="idemp-happy-1",
        )

        assert result["status"] == "completed"
        assert result["meta"]["degraded"] is False
        assert result["summary"]["matched_quest_count"] >= 1
        assert result["summary"]["skill_award_count"] >= 1
        assert len(result["personality_messages"]) == 1
        message = result["personality_messages"][0]
        assert message["id"] == result["message_id"]
        assert message["personality"] == result["personality"]
        assert message["message_text"] == result["message"]
        assert message["logical_slot_key"] == "primary"
        assert message["multi_personality"] == {
            "is_primary": True,
            "primary_personality": message["personality"],
            "impact_multiplier": 1.0,
        }

        structured = (
            db.query(JournalEntryStructured)
            .filter(
                JournalEntryStructured.user_id == ids.user_id,
                JournalEntryStructured.entry_id == ids.entry_id,
            )
            .one_or_none()
        )
        assert structured is not None

        assert db.query(XpAward).count() >= 1
        assert db.query(ProcessingJob).count() == 1
        assert db.query(OutboxEvent).count() == 1
        assert result["quest_result"]["instant_quest_id"] is not None
        assert result["quest_result"]["streak_quest_ids"]

        instant_quest = (
            db.query(Quest)
            .filter(
                Quest.user_id == ids.user_id,
                Quest.id == result["quest_result"]["instant_quest_id"],
            )
            .one_or_none()
        )
        assert instant_quest is not None
        assert instant_quest.entry_id == ids.entry_id

        streak_quests = (
            db.query(Quest)
            .filter(
                Quest.user_id == ids.user_id,
                Quest.id.in_(result["quest_result"]["streak_quest_ids"]),
            )
            .all()
        )
        assert len(streak_quests) == len(result["quest_result"]["streak_quest_ids"])
        assert all(quest.completion_type == "streak" for quest in streak_quests)


def test_pipeline_degrades_when_ollama_is_unavailable():
    with _make_db() as db:
        ids = _seed_core_graph(db)

        processor = PipelineProcessor(
            db=db, ollama=_DownOllama(), qdrant=_HealthyQdrant()
        )
        result = processor.process_entry(
            entry_id=ids.entry_id,
            user_id=ids.user_id,
            idempotency_key="idemp-ollama-down-1",
        )

        assert result["status"] == "completed"
        assert result["meta"]["degraded"] is True
        assert "STEP_05_EMBEDDING" in result["meta"]["degraded_codes"]


def test_pipeline_degrades_when_qdrant_is_unavailable():
    with _make_db() as db:
        ids = _seed_core_graph(db)

        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_DownQdrant()
        )
        result = processor.process_entry(
            entry_id=ids.entry_id,
            user_id=ids.user_id,
            idempotency_key="idemp-qdrant-down-1",
        )

        assert result["status"] == "completed"
        assert result["meta"]["degraded"] is True
        assert "STEP_06_RAG_SEARCH" in result["meta"]["degraded_codes"]


def test_pipeline_idempotency_replay_avoids_duplicate_side_effects():
    with _make_db() as db:
        ids = _seed_core_graph(db)

        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_HealthyQdrant()
        )

        first = processor.process_entry(
            entry_id=ids.entry_id,
            user_id=ids.user_id,
            idempotency_key="idemp-replay-1",
        )
        awards_after_first = db.query(XpAward).count()
        outbox_after_first = db.query(OutboxEvent).count()

        second = processor.process_entry(
            entry_id=ids.entry_id,
            user_id=ids.user_id,
            idempotency_key="idemp-replay-1",
        )

        assert first["status"] == "completed"
        assert second["replayed"] is True
        assert db.query(XpAward).count() == awards_after_first
        assert db.query(OutboxEvent).count() == outbox_after_first
        assert (
            db.query(EntryIdempotencyClaim)
            .filter(
                EntryIdempotencyClaim.user_id == ids.user_id,
                EntryIdempotencyClaim.idempotency_key == "idemp-replay-1",
            )
            .count()
            == 1
        )


def test_pipeline_smoke_latency_under_two_seconds_with_local_stubs():
    with _make_db() as db:
        ids = _seed_core_graph(db)

        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_HealthyQdrant()
        )

        started = time.perf_counter()
        result = processor.process_entry(
            entry_id=ids.entry_id,
            user_id=ids.user_id,
            idempotency_key="idemp-latency-1",
        )
        elapsed = time.perf_counter() - started

        assert result["status"] == "completed"
        assert elapsed < 2.0
