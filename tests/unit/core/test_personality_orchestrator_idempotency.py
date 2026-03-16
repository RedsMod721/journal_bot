from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.personality_orchestrator import PersonalityOrchestrator
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.journal_entry import JournalEntry
from src.db.models.personality import PersonalityMemory, PersonalityMessage, PersonalityState
from src.db.models.user import User


class _NullRAGService:
    def retrieve_relevant_context(self, **_kwargs):
        return []

    def retrieve_safety_resources(self, **_kwargs):
        return []


def _make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.info["engine"] = engine
    return session


def test_apply_entry_personality_plan_is_insert_first_and_replay_safe() -> None:
    db = _make_session()
    try:
        user = User(
            id="11111111-1111-1111-1111-111111111199",
            username="personality-test",
            email="personality-test@example.com",
            password_hash="hash",
            home_country="FR",
        )
        entry = JournalEntry(
            id="22222222-2222-2222-2222-222222222299",
            user_id=user.id,
            content="I finished a hard training session and want to keep momentum.",
            entry_type="text",
            status="processing",
        )
        db.add_all([user, entry])
        db.commit()

        orchestrator = PersonalityOrchestrator(db, rag_service=_NullRAGService())
        first_now = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        second_now = first_now + timedelta(days=1)
        plan = {
            "personality": "coach",
            "selection_reason": "test_selection",
            "selection_factors": {"seed": "fixed-seed"},
            "message": "You kept showing up, and that matters.",
            "message_type": "entry_feedback",
            "context_data": {
                "generation_mode": "template",
                "citations": [],
                "template_key": "coach.entry_feedback",
            },
            "generation_mode": "template",
            "citations": [],
            "fallback_reason": None,
            "template_key": "coach.entry_feedback",
            "selector_version": 7,
            "selector_seed_hash": "seed-hash",
            "logical_slot_key": "primary",
            "thread_memories": [
                {"role": "user", "content": entry.content},
                {
                    "role": "assistant",
                    "content": "You kept showing up, and that matters.",
                    "personality": "coach",
                    "message_type": "entry_feedback",
                },
            ],
            "short_term_summary": "Entry processed by coach.",
            "pipeline_version": "test-v1",
        }

        first = orchestrator.apply_entry_personality_plan(
            user_id=user.id,
            entry_id=entry.id,
            entry_text=entry.content,
            plan=plan,
            now_utc=first_now,
        )
        db.commit()

        first_message = db.query(PersonalityMessage).one()
        memories = (
            db.query(PersonalityMemory)
            .filter(PersonalityMemory.user_id == user.id)
            .order_by(PersonalityMemory.tier, PersonalityMemory.key)
            .all()
        )
        state = db.query(PersonalityState).filter(PersonalityState.user_id == user.id).one()

        expected_thread_expiry = (first_now + timedelta(hours=2)).replace(tzinfo=None)
        expected_short_term_expiry = (
            first_now + timedelta(days=state.memory_short_term_days)
        ).replace(tzinfo=None)
        memory_snapshot = {
            memory.key: memory.expires_at
            for memory in memories
        }

        second = orchestrator.apply_entry_personality_plan(
            user_id=user.id,
            entry_id=entry.id,
            entry_text=entry.content,
            plan=plan,
            now_utc=second_now,
        )
        db.commit()

        messages_after = db.query(PersonalityMessage).all()
        memories_after = (
            db.query(PersonalityMemory)
            .filter(PersonalityMemory.user_id == user.id)
            .order_by(PersonalityMemory.tier, PersonalityMemory.key)
            .all()
        )
        state_after = db.query(PersonalityState).filter(PersonalityState.user_id == user.id).one()

        assert first["inserted"] is True
        assert second["inserted"] is False
        assert first["message_id"] == second["message_id"] == first_message.id
        assert len(messages_after) == 1
        assert len(memories_after) == 3
        assert state_after.active_personality == "coach"
        assert state_after.last_switched_at == first_now.replace(tzinfo=None)
        assert state_after.last_selection_factors == state.last_selection_factors

        for memory in memories_after:
            assert memory.expires_at == memory_snapshot[memory.key]

        assert memory_snapshot[f"thread:{entry.id}:user"] == expected_thread_expiry
        assert (
            memory_snapshot[f"thread:{entry.id}:assistant:entry_feedback:coach"]
            == expected_thread_expiry
        )
        assert memory_snapshot[f"short_term:{entry.id}:summary"] == expected_short_term_expiry
    finally:
        engine = db.info.pop("engine", None)
        db.close()
        if engine is not None:
            engine.dispose()
