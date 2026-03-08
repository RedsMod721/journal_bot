"""Week 3 performance smoke tests for pipeline ACK/completion envelope."""

from __future__ import annotations

import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai.pipeline import PipelineProcessor
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.journal_entry import JournalEntry
from src.db.models.quest import Quest
from src.db.models.skill import Skill
from src.db.models.user import User


class _StubOllama:
    def health(self):
        return {"connected": True, "model_available": True, "models": ["stub"]}

    def embed(self, _text: str):
        return [0.01] * 384


class _StubQdrant:
    vector_size = 384

    def ensure_collection(self):
        return None

    def search(self, _vector, limit=5):
        return []


def test_pipeline_completion_smoke_under_30_seconds():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_local() as db:
        user = User(
            id="00000000-0000-0000-0000-000000000201",
            email="perf@example.com",
            password_hash="x",
            home_country="US",
        )
        skill = Skill(
            id="00000000-0000-0000-0000-000000000202",
            user_id=user.id,
            name="Focus",
            canonical_name="focus",
        )
        quest = Quest(
            id="00000000-0000-0000-0000-000000000203",
            user_id=user.id,
            skill_id=skill.id,
            name="Focus Session",
            quest_type="instant",
            completion_type="one_time",
            status="active",
            required_progress=1,
            current_progress=0,
            base_xp=480,
        )
        entry = JournalEntry(
            id="00000000-0000-0000-0000-000000000204",
            user_id=user.id,
            content="I did a focused deep-work session.",
            entry_type="text",
            status="pending",
            question_state="none",
        )
        db.add_all([user, skill, quest, entry])
        db.commit()

        processor = PipelineProcessor(db=db, ollama=_StubOllama(), qdrant=_StubQdrant())

        started = time.perf_counter()
        result = processor.process_entry(
            entry_id=entry.id,
            user_id=user.id,
            idempotency_key="perf-key-1",
        )
        elapsed = time.perf_counter() - started

        assert result["status"] == "completed"
        assert elapsed < 30.0
