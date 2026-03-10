"""Additional branch coverage for src.ai.pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai.cache import StepCache
from src.ai.pipeline import PipelineProcessor, PipelineStepError
from src.ai.steps import embedding, rag
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.journal_entry import JournalEntry
from src.db.models.processing import EntryIdempotencyClaim, OutboxEvent, ProcessingJob
from src.db.models.quest import Quest
from src.db.models.skill import Skill, SkillThemeMapping, Theme
from src.db.models.user import User


class _HealthyOllama:
    model = "llama3.2:latest"

    def health(self):
        return {"connected": True, "model_available": True, "models": [self.model]}

    def embed(self, _text: str):
        return [0.1] * 8

    def generate_json(self, _prompt: str) -> dict:
        return {
            "response": '{"insight_text": "Keep it up!", "category": "general", "confidence": 0.8}'
        }


class _HealthyQdrant:
    vector_size = 8
    collection = "rag_documents"

    def ensure_collection(self):
        return None

    def search(self, _vector, limit=5):
        return [{"point_id": "p1", "score": 0.9, "payload": {}}][:limit]


class _DownOllama:
    model = "llama3.2:latest"

    def health(self):
        return {
            "connected": False,
            "model_available": False,
            "models": [],
            "error": "offline",
        }

    def embed(self, _text: str):
        raise RuntimeError("ollama unavailable")


class _DownQdrant:
    vector_size = 8
    collection = "rag_documents"

    def ensure_collection(self):
        raise RuntimeError("qdrant unavailable")

    def search(self, _vector, limit=5):
        raise RuntimeError("qdrant unavailable")


@dataclass
class _FixtureIds:
    user_id: str
    entry_id: str


def _make_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return local()


def _seed(db: Session) -> _FixtureIds:
    user = User(
        id="00000000-0000-0000-0000-000000000201",
        email="pipeline-branch@example.com",
        password_hash="x",
        home_country="US",
    )
    db.add(user)

    skill = Skill(
        id="00000000-0000-0000-0000-000000000202",
        user_id=user.id,
        name="Python Programming",
        canonical_name="python programming",
        level=1,
        rank="F",
        xp=0,
    )
    theme = Theme(
        id="00000000-0000-0000-0000-000000000203",
        user_id=user.id,
        name="Professional",
        level=1,
        rank="F",
        xp=0,
    )
    db.add(skill)
    db.add(theme)
    db.flush()
    db.add(
        SkillThemeMapping(
            id="00000000-0000-0000-0000-000000000204",
            user_id=user.id,
            skill_id=skill.id,
            theme_id=theme.id,
        )
    )
    db.add(
        Quest(
            id="00000000-0000-0000-0000-000000000205",
            user_id=user.id,
            skill_id=skill.id,
            name="Quest",
            quest_type="instant",
            completion_type="one_time",
            base_xp=480,
            status="active",
            required_progress=1,
            current_progress=0,
        )
    )
    entry = JournalEntry(
        id="00000000-0000-0000-0000-000000000206",
        user_id=user.id,
        content="I code and walk and talk with team.",
        entry_type="text",
        status="pending",
        question_state="none",
    )
    db.add(entry)
    db.commit()
    return _FixtureIds(user_id=user.id, entry_id=entry.id)


def test_build_default_qdrant_fallback_when_adapter_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    with _make_db() as db:
        ids = _seed(db)

        def _raise():
            raise RuntimeError("qdrant down")

        monkeypatch.setattr("src.ai.pipeline.QdrantClientAdapter", _raise)
        processor = PipelineProcessor(db=db, ollama=_HealthyOllama(), qdrant=None)

        assert processor.qdrant.search([0.0] * 8) == []
        result = processor.process_entry(
            entry_id=ids.entry_id,
            user_id=ids.user_id,
            idempotency_key="idemp-fallback-qdrant",
        )
        assert result["status"] == "completed"


def test_process_entry_raises_entry_not_found():
    with _make_db() as db:
        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_HealthyQdrant()
        )
        with pytest.raises(PipelineStepError, match="not found"):
            processor.process_entry(
                entry_id="00000000-0000-0000-0000-000000009999",
                user_id="00000000-0000-0000-0000-000000009998",
                idempotency_key="idemp-missing",
            )


def test_process_entry_failure_path_records_failed_job_and_claim(
    monkeypatch: pytest.MonkeyPatch,
):
    with _make_db() as db:
        ids = _seed(db)
        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_HealthyQdrant()
        )

        def _boom(**_kwargs):
            raise RuntimeError("structured crash")

        # Patch a mandatory (non-degradable) step — structured data persistence
        # (step 08) has allow_degraded=False, so failures bubble up as PipelineStepError.
        # (Step 07 / signals is allow_degraded=True and would degrade silently instead.)
        monkeypatch.setattr("src.ai.steps.structured.run", _boom)

        with pytest.raises(PipelineStepError, match="structured crash"):
            processor.process_entry(
                entry_id=ids.entry_id,
                user_id=ids.user_id,
                idempotency_key="idemp-fail-path",
            )

        job = db.query(ProcessingJob).one()
        claim = db.query(EntryIdempotencyClaim).one()
        entry = db.query(JournalEntry).filter(JournalEntry.id == ids.entry_id).one()
        failed_events = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.event_type == "entry.processing_failed")
            .all()
        )

        assert job.status == "failed"
        assert claim.status == "failed"
        assert entry.status == "failed"
        assert failed_events


def test_record_failure_creates_claim_if_missing_and_no_job():
    with _make_db() as db:
        ids = _seed(db)
        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_HealthyQdrant()
        )

        processor._record_failure(
            job_id="00000000-0000-0000-0000-000000001111",
            user_id=ids.user_id,
            entry_id=ids.entry_id,
            key="idemp-missing-claim",
            processing_run_id="run-missing-claim",
            error="forced failure",
            error_code="PIPELINE_EXCEPTION",
        )

        claim = (
            db.query(EntryIdempotencyClaim)
            .filter(EntryIdempotencyClaim.idempotency_key == "idemp-missing-claim")
            .one()
        )
        assert claim.status == "failed"


def test_step_embedding_raises_when_ollama_disconnected():
    # Step logic lives in src.ai.steps.embedding — test the module directly.
    with pytest.raises(RuntimeError, match="ollama unavailable"):
        embedding.run(
            entry_id="entry-x",
            normalized_text="text",
            ollama_health={"connected": False},
            ollama=_HealthyOllama(),
            cache=StepCache(),
        )


def test_step_rag_search_empty_vector_returns_fallback():
    # Step logic lives in src.ai.steps.rag — test the module directly.
    out = rag.run(vector=[], qdrant=_HealthyQdrant())
    assert out["hits"] == []
    assert out["hit_count"] == 0
    assert out["fallback"] is True
    assert out["from_cache"] is False


@pytest.mark.parametrize(
    ("ollama", "qdrant", "expected_codes"),
    [
        (_DownOllama(), _HealthyQdrant(), {"STEP_05_EMBEDDING"}),
        (_HealthyOllama(), _DownQdrant(), {"STEP_06_RAG_SEARCH"}),
        (
            _DownOllama(),
            _DownQdrant(),
            {"STEP_05_EMBEDDING", "STEP_06_RAG_SEARCH"},
        ),
    ],
)
def test_degraded_step_codes_table_driven(ollama, qdrant, expected_codes):
    with _make_db() as db:
        ids = _seed(db)
        processor = PipelineProcessor(db=db, ollama=ollama, qdrant=qdrant)
        result = processor.process_entry(
            entry_id=ids.entry_id,
            user_id=ids.user_id,
            idempotency_key=f"idemp-degraded-{len(expected_codes)}",
        )

        assert result["meta"]["degraded"] is True
        assert set(result["meta"]["degraded_codes"]) == expected_codes


def test_claim_replay_collision_returns_existing_claim_payload_without_duplication():
    with _make_db() as db:
        ids = _seed(db)
        db.add(
            EntryIdempotencyClaim(
                user_id=ids.user_id,
                idempotency_key="idemp-collision",
                entry_id=ids.entry_id,
                processing_run_id="run-existing-collision",
                status="claimed",
            )
        )
        db.commit()

        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_HealthyQdrant()
        )
        replay = processor.process_entry(
            entry_id=ids.entry_id,
            user_id=ids.user_id,
            idempotency_key="idemp-collision",
        )

        assert replay["replayed"] is True
        assert replay["idempotency_key"] == "idemp-collision"
        assert db.query(ProcessingJob).count() == 0
        assert db.query(EntryIdempotencyClaim).count() == 1


def test_malformed_structured_payload_triggers_failure_recording(
    monkeypatch: pytest.MonkeyPatch,
):
    with _make_db() as db:
        ids = _seed(db)
        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_HealthyQdrant()
        )

        def _malformed(**_kwargs):
            # Returns a detection dict that is missing required keys
            # (dominant_emotions, energy_level, etc.), causing the structured
            # step to raise a KeyError and the pipeline to record a failure.
            return {
                "detected_skills": ["Python Programming"],
                "detected_activities": ["code"],
            }

        # Step logic lives in src.ai.steps.signals; patch at the module level.
        monkeypatch.setattr("src.ai.steps.signals.run", _malformed)

        with pytest.raises(PipelineStepError):
            processor.process_entry(
                entry_id=ids.entry_id,
                user_id=ids.user_id,
                idempotency_key="idemp-malformed-structured",
            )

        claim = (
            db.query(EntryIdempotencyClaim)
            .filter(
                EntryIdempotencyClaim.user_id == ids.user_id,
                EntryIdempotencyClaim.idempotency_key == "idemp-malformed-structured",
            )
            .one()
        )
        assert claim.status == "failed"


def test_outbox_emission_failure_handling_records_processing_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    with _make_db() as db:
        ids = _seed(db)
        processor = PipelineProcessor(
            db=db, ollama=_HealthyOllama(), qdrant=_HealthyQdrant()
        )

        call_count = {"n": 0}

        def _flaky_emit(*, user_id: str, event_type: str, payload: dict):
            call_count["n"] += 1
            if call_count["n"] == 1 and event_type == "entry.processed":
                raise RuntimeError("outbox write failed")
            return None

        monkeypatch.setattr(processor, "_emit_outbox_event", _flaky_emit)

        with pytest.raises(RuntimeError, match="outbox write failed"):
            processor.process_entry(
                entry_id=ids.entry_id,
                user_id=ids.user_id,
                idempotency_key="idemp-outbox-failure",
            )

        job = db.query(ProcessingJob).one()
        claim = (
            db.query(EntryIdempotencyClaim)
            .filter(EntryIdempotencyClaim.idempotency_key == "idemp-outbox-failure")
            .one()
        )
        entry = db.query(JournalEntry).filter(JournalEntry.id == ids.entry_id).one()

        assert job.status == "failed"
        assert claim.status == "failed"
        assert entry.status == "failed"
