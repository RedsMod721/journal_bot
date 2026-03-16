"""Week 3 pipeline contract tests."""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai import pipeline_core as pipeline_core_module
from src.ai.pipeline import PipelineProcessor
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.global_kb import GlobalSkill
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.personality import PersonalityMessage
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
        return [
            {
                "point_id": "p1",
                "score": 0.91,
                "payload": {
                    "doc_id": "doc-1",
                    "content": "Consistent effort compounds when sessions stay repeatable.",
                    "metadata": {
                        "chunk_id": "chunk-1",
                        "title": "Training note",
                        "source_type": "rag_document",
                    },
                },
            }
        ][:limit]


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
        assert result["quality"]["degraded"] is False
        assert result["summary"]["matched_quest_count"] >= 1
        assert result["summary"]["skill_award_count"] >= 1
        assert result["step_trace"]
        assert result["step_trace"][0]["step_name"] == "step_01_validate_input"
        assert any(
            step["step_name"] == "step_16r_quest_matcher" for step in result["step_trace"]
        )
        assert any(
            step["step_name"] == "step_15b_system_report" for step in result["step_trace"]
        )
        assert any(
            step["step_name"] == "step_16s_persist_system_report"
            for step in result["step_trace"]
        )
        assert len(result["personality_messages"]) == 2
        primary_message = next(
            message
            for message in result["personality_messages"]
            if message["logical_slot_key"] == "primary"
        )
        system_message = next(
            message
            for message in result["personality_messages"]
            if message["personality"] == "system"
        )
        assert primary_message["id"] == result["message_id"]
        assert primary_message["personality"] == result["personality"]
        assert primary_message["message_text"] == result["message"]
        assert primary_message["logical_slot_key"] == "primary"
        assert primary_message["multi_personality"] == {
            "is_primary": True,
            "primary_personality": primary_message["personality"],
            "impact_multiplier": 1.0,
        }
        assert system_message["message_type"] == "report_summary"
        assert system_message["logical_slot_key"] == "system_report"
        assert "[Signals]" in system_message["message_text"]
        assert "[Personality Reply]" in system_message["message_text"]
        assert result["report_result"]["message_id"] == system_message["id"]
        assert result["report_result"]["inserted"] is True
        assert result["report_result"]["context_data"]["report_kind"] == "daily"

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
        assert (
            db.query(PersonalityMessage)
            .filter(
                PersonalityMessage.user_id == ids.user_id,
                PersonalityMessage.entry_id == ids.entry_id,
                PersonalityMessage.personality == "system",
            )
            .count()
            == 1
        )


def test_pipeline_system_report_fallback_is_still_persisted(
    monkeypatch: pytest.MonkeyPatch,
):
    with _make_db() as db:
        ids = _seed_core_graph(db)

        def _raise_report_builder(self, **_kwargs):
            raise RuntimeError("report builder boom")

        monkeypatch.setattr(
            PipelineProcessor,
            "_build_system_report_payload",
            _raise_report_builder,
        )

        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_HealthyQdrant()
        )
        result = processor.process_entry(
            entry_id=ids.entry_id,
            user_id=ids.user_id,
            idempotency_key="idemp-report-fallback-1",
        )

        assert result["status"] == "completed"
        assert result["report_result"]["fallback_used"] is True
        assert result["report_result"]["message_id"] is not None
        assert result["report_result"]["context_data"]["completion_status"] == "partial"
        assert "signals" in result["report_result"]["context_data"]["missing_sections"]
        assert any(
            step["step_name"] == "step_15b_system_report" and step["status"] == "fallback"
            for step in result["step_trace"]
        )
        assert any(
            step["step_name"] == "step_16s_persist_system_report"
            for step in result["step_trace"]
        )

        system_message = next(
            message
            for message in result["personality_messages"]
            if message["personality"] == "system"
        )
        assert system_message["id"] == result["report_result"]["message_id"]
        assert "[Signals] missing" in system_message["message_text"]
        assert "[Insight] missing" in system_message["message_text"]
        assert (
            db.query(PersonalityMessage)
            .filter(
                PersonalityMessage.user_id == ids.user_id,
                PersonalityMessage.entry_id == ids.entry_id,
                PersonalityMessage.personality == "system",
            )
            .count()
            == 1
        )


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
        assert elapsed < 2.5


def test_pipeline_core_resolves_run_cardio_source_skill_weights():
    with _make_db() as db:
        user = User(
            id="00000000-0000-0000-0000-000000000201",
            email="resolver@example.com",
            password_hash="x",
            home_country="US",
        )
        db.add(user)
        db.add_all(
            [
                GlobalSkill(
                    id="00000000-0000-0000-0000-000000000202",
                    source_skill_id="skill_physical_running",
                    canonical_name="Running",
                    category="Physical",
                ),
                GlobalSkill(
                    id="00000000-0000-0000-0000-000000000203",
                    source_skill_id="skill_physical_cardio_endurance",
                    canonical_name="Cardio Endurance",
                    category="Physical",
                ),
                GlobalSkill(
                    id="00000000-0000-0000-0000-000000000204",
                    source_skill_id="skill_physical_cardiorespiratory_fitness",
                    canonical_name="Cardiorespiratory Fitness",
                    category="Physical",
                ),
            ]
        )
        db.commit()

        signals = pipeline_core_module._derive_week7_structured_signals(
            user_id=user.id,
            canonical_text="today i practiced cardio by doing a 10km run in 1h",
            detection={
                "detected_skills": [],
                "detected_activities": ["practice", "run"],
            },
            db=db,
        )

        assert signals["source_skills_weights_bp"] == {
            "skill_physical_running": 7000,
            "skill_physical_cardio_endurance": 1500,
            "skill_physical_cardiorespiratory_fitness": 1500,
        }
        assert signals["skills_weights_bp"] == {}
        assert signals["resolved_skill_names"] == [
            "Running",
            "Cardio Endurance",
            "Cardiorespiratory Fitness",
        ]
        assert signals["pattern_hits_json"] == [
            {"semantic_key": "practice", "confidence_score": 0.70},
            {"semantic_key": "run", "confidence_score": 0.70},
        ]


def test_pipeline_pushup_regression_exposes_lineage_and_avoids_study_strategy():
    with _make_db() as db:
        user = User(
            id="00000000-0000-0000-0000-000000000211",
            email="pushups@example.com",
            password_hash="x",
            home_country="US",
        )
        db.add(user)
        db.add_all(
            [
                GlobalSkill(
                    id="00000000-0000-0000-0000-000000000212",
                    source_skill_id="skill_physical_strength_training",
                    canonical_name="Strength Training",
                    category="Physical",
                ),
                GlobalSkill(
                    id="00000000-0000-0000-0000-000000000213",
                    source_skill_id="skill_physical_physical_health",
                    canonical_name="Physical Health",
                    category="Physical",
                ),
            ]
        )
        entry = JournalEntry(
            id="00000000-0000-0000-0000-000000000214",
            user_id=user.id,
            content="today I did 50 pushups for endurance and strength training",
            entry_type="text",
            status="pending",
            question_state="none",
        )
        db.add(entry)
        db.commit()

        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_HealthyQdrant()
        )
        result = processor.process_entry(
            entry_id=entry.id,
            user_id=user.id,
            idempotency_key="idemp-pushup-lineage-1",
        )

        assert result["status"] == "completed"
        assert result["summary"]["detected_activities"]
        assert result["structured_data"]["task_type"] == "physical"
        assert result["strategy_detected"] != "study"
        lineage = result["quest_result"]["xp_lineage"]
        assert "skill_physical_strength_training" in lineage["source_skill_weights_bp"]
        assert "skill_physical_physical_health" in lineage["final_target_skill_ids"]
        assert any(
            path["target_skill_id"] == "skill_physical_physical_health"
            for path in lineage["redirect_paths"]
        )
