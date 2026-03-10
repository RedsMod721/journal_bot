"""End-to-end integration tests for journal processing pipeline."""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai.pipeline import JournalEntryPipeline
from src.api.routes.journal import JournalEntryCreate
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.global_kb import GlobalSkill
from src.db.models.journal_entry import JournalEntry
from src.db.models.quest import Quest
from src.db.models.skill import Skill, SkillThemeMapping, Theme
from src.db.models.user import User
from src.db.models.xp import XpAward


pytestmark = [pytest.mark.integration]


class _HealthyOllama:
    model = "llama3.2:3b"

    def health(self) -> dict:
        return {
            "connected": True,
            "model_available": True,
            "models": [self.model],
        }

    def embed(self, _text: str) -> list[float]:
        return [0.01] * 384

    def generate_json(self, _prompt: str) -> dict:
        return {
            "response": '{"insight_text":"Solid progress.","category":"skill_development","confidence":0.9}'
        }


class _DownOllama:
    model = "llama3.2:3b"

    def health(self) -> dict:
        return {
            "connected": False,
            "model_available": False,
            "models": [],
            "error": "connection refused",
        }

    def embed(self, _text: str) -> list[float]:
        raise RuntimeError("ollama unavailable")


class _HealthyQdrant:
    vector_size = 384
    collection = "rag_documents"

    def ensure_collection(self) -> None:
        return None

    def search(self, _vector: list[float], limit: int = 5) -> list[dict]:
        return [{"point_id": "p1", "score": 0.95, "payload": {"title": "doc"}}][:limit]


@pytest.fixture
def test_db() -> Session:
    """Create in-memory DB with all src models and seed global skill catalog."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()

    session.add_all(
        [
            GlobalSkill(
                id="00000000-0000-0000-0000-00000000a101",
                source_skill_id="skill_python",
                canonical_name="Python Programming",
                category="Professional",
            ),
            GlobalSkill(
                id="00000000-0000-0000-0000-00000000a102",
                source_skill_id="skill_running",
                canonical_name="Cardio Running",
                category="Physical",
            ),
            GlobalSkill(
                id="00000000-0000-0000-0000-00000000a103",
                source_skill_id="skill_reading",
                canonical_name="Reading",
                category="Mental",
            ),
        ]
    )
    session.commit()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def test_user(test_db: Session) -> User:
    """Create a user matching src.db.models.user required fields."""
    user = User(
        id="00000000-0000-0000-0000-000000000901",
        username="testuser",
        email="test@example.com",
        password_hash="not-used-in-tests",
        home_country="US",
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def test_entry(test_db: Session, test_user: User) -> JournalEntry:
    """Create one entry plus skill/theme/quest graph so XP and theme propagation can occur."""
    skill = Skill(
        id="00000000-0000-0000-0000-000000000902",
        user_id=test_user.id,
        name="Python Programming",
        canonical_name="python programming",
        xp=0,
        level=1,
        rank="F",
    )
    theme = Theme(
        id="00000000-0000-0000-0000-000000000903",
        user_id=test_user.id,
        name="Professional",
        xp=0,
        level=1,
        rank="F",
    )
    test_db.add_all([skill, theme])
    test_db.flush()

    test_db.add(
        SkillThemeMapping(
            id="00000000-0000-0000-0000-000000000904",
            user_id=test_user.id,
            skill_id=skill.id,
            theme_id=theme.id,
        )
    )

    test_db.add(
        Quest(
            id="00000000-0000-0000-0000-000000000905",
            user_id=test_user.id,
            skill_id=skill.id,
            name="Ship Python work",
            quest_type="instant",
            completion_type="one_time",
            base_xp=480,
            status="active",
            required_progress=1,
            current_progress=0,
        )
    )

    entry = JournalEntry(
        id="00000000-0000-0000-0000-000000000906",
        user_id=test_user.id,
        content=(
            "Today I coded for two focused hours on my Python project and finished tests, "
            "then I reviewed architecture notes with the team."
        ),
        entry_type="text",
        status="pending",
        question_state="none",
    )
    test_db.add(entry)
    test_db.commit()
    return entry


class TestPipelineE2E:
    """End-to-end pipeline tests using real DB models and async facade."""

    @pytest.mark.asyncio
    async def test_successful_entry_processing(
        self,
        test_db: Session,
        test_user: User,
        test_entry: JournalEntry,
    ) -> None:
        pipeline = JournalEntryPipeline(
            db_session=test_db,
            ollama_client=_HealthyOllama(),
            qdrant_client=_HealthyQdrant(),
        )

        result = await pipeline.process_entry(test_entry.id, test_user.id)

        assert result["status"] == "completed"
        assert result["entry_id"] == test_entry.id
        assert result["summary"]["matched_quest_count"] >= 1
        assert result["summary"]["skill_award_count"] >= 1

        test_db.refresh(test_entry)
        assert test_entry.status == "completed"
        assert test_entry.processed_at is not None
        assert test_entry.processing_duration_ms is not None
        assert test_entry.processing_duration_ms < 30000

    @pytest.mark.asyncio
    async def test_xp_awarded_to_skills(
        self,
        test_db: Session,
        test_user: User,
        test_entry: JournalEntry,
    ) -> None:
        pipeline = JournalEntryPipeline(
            db_session=test_db,
            ollama_client=_HealthyOllama(),
            qdrant_client=_HealthyQdrant(),
        )

        await pipeline.process_entry(test_entry.id, test_user.id)

        skill_awards = (
            test_db.query(XpAward)
            .filter(
                XpAward.user_id == test_user.id,
                XpAward.skill_id.isnot(None),
            )
            .all()
        )
        assert len(skill_awards) >= 1
        assert all(a.amount > 0 for a in skill_awards)

        skills = test_db.query(Skill).filter(Skill.user_id == test_user.id).all()
        assert len(skills) >= 1
        assert any(s.xp > 0 for s in skills)
        assert all(s.level >= 1 for s in skills)
        assert any(s.last_activity_at is not None for s in skills)

    @pytest.mark.asyncio
    async def test_theme_propagation(
        self,
        test_db: Session,
        test_user: User,
        test_entry: JournalEntry,
    ) -> None:
        pipeline = JournalEntryPipeline(
            db_session=test_db,
            ollama_client=_HealthyOllama(),
            qdrant_client=_HealthyQdrant(),
        )

        await pipeline.process_entry(test_entry.id, test_user.id)

        skill_awards = (
            test_db.query(XpAward)
            .filter(XpAward.user_id == test_user.id, XpAward.skill_id.isnot(None))
            .all()
        )
        theme_awards = (
            test_db.query(XpAward)
            .filter(XpAward.user_id == test_user.id, XpAward.theme_id.isnot(None))
            .all()
        )

        assert len(skill_awards) >= 1
        assert len(theme_awards) >= 1
        assert all(a.amount >= 1 for a in theme_awards)

        # With one theme mapping, each theme award should be max(1, floor(skill_xp * 0.001)).
        expected_amounts = {max(1, int(a.amount * 0.001)) for a in skill_awards}
        assert {a.amount for a in theme_awards}.issubset(expected_amounts)

        themes = test_db.query(Theme).filter(Theme.user_id == test_user.id).all()
        assert len(themes) >= 1
        assert any(t.xp >= 1 for t in themes)

    @pytest.mark.asyncio
    async def test_pipeline_with_ollama_unavailable(
        self,
        test_db: Session,
        test_user: User,
        test_entry: JournalEntry,
    ) -> None:
        pipeline = JournalEntryPipeline(
            db_session=test_db,
            ollama_client=_DownOllama(),
            qdrant_client=_HealthyQdrant(),
        )

        result = await pipeline.process_entry(test_entry.id, test_user.id)

        assert result["status"] == "completed"
        assert result["meta"]["degraded"] is True
        assert "STEP_05_EMBEDDING" in result["meta"]["degraded_codes"]

    @pytest.mark.asyncio
    async def test_pipeline_performance_under_30s(
        self,
        test_db: Session,
        test_user: User,
        test_entry: JournalEntry,
    ) -> None:
        pipeline = JournalEntryPipeline(
            db_session=test_db,
            ollama_client=_HealthyOllama(),
            qdrant_client=_HealthyQdrant(),
        )

        start = time.perf_counter()
        result = await pipeline.process_entry(test_entry.id, test_user.id)
        elapsed = time.perf_counter() - start

        assert result["status"] == "completed"
        assert elapsed < 30

        test_db.refresh(test_entry)
        assert test_entry.processing_duration_ms is not None
        assert test_entry.processing_duration_ms < 30000

    def test_validation_rejects_too_short_entry(self) -> None:
        with pytest.raises(ValidationError, match="Minimum 2 words required"):
            JournalEntryCreate(
                user_id="00000000-0000-0000-0000-00000000ffff",
                raw_text="solo",
            )
