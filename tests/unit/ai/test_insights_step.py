"""Unit tests for src.ai.steps.insights."""

from __future__ import annotations

# ruff: noqa: E402

import sys
import types

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_stub = types.ModuleType("sentence_transformers")
_stub.SentenceTransformer = object  # type: ignore[attr-defined]
sys.modules.setdefault("sentence_transformers", _stub)

from src.ai.cache import StepCache  # noqa: E402
from src.ai.steps import insights  # noqa: E402
from src.db.base import Base  # noqa: E402
import src.db.models  # noqa: E402,F401
from src.db.models.insight import Insight, InsightEvidence  # noqa: E402
from src.db.models.journal_entry import JournalEntry  # noqa: E402
from src.db.models.user import User  # noqa: E402


class _OllamaStub:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    def generate_json(self, _prompt: str) -> dict:
        self.calls += 1
        return {"response": self.response}


def _make_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return local()


def _seed_user_and_entry(db: Session) -> tuple[str, str]:
    user = User(
        id="00000000-0000-0000-0000-000000000301",
        email="insights-step@example.com",
        password_hash="x",
        home_country="US",
    )
    entry = JournalEntry(
        id="00000000-0000-0000-0000-000000000302",
        user_id=user.id,
        content="I practiced coding.",
        entry_type="text",
        status="pending",
        question_state="none",
    )
    db.add(user)
    db.add(entry)
    db.commit()
    return user.id, entry.id


def test_insights_without_retrieval_context_are_suppressed_without_persisting() -> None:
    with _make_db() as db:
        user_id, entry_id = _seed_user_and_entry(db)
        ollama = _OllamaStub(response='{"insight_text":"ignored"}')

        out = insights.run(
            user_id=user_id,
            entry_id=entry_id,
            canonical_text="Practiced consistently",
            rag_hits=[],
            detection={"task_type": "practice", "detected_skills": []},
            ollama_health={"connected": False},
            ollama=ollama,
            db=db,
            cache=None,
        )

        assert out["from_ollama"] is False
        assert out["from_cache"] is False
        assert out["generated"] is False
        assert out["suppression_reason"] == "RAG_EMPTY_CONTEXT"
        assert ollama.calls == 0
        assert db.query(Insight).count() == 0
        assert db.query(InsightEvidence).count() == 0


def test_insights_llm_parse_sanitizes_category_and_confidence() -> None:
    with _make_db() as db:
        user_id, entry_id = _seed_user_and_entry(db)
        ollama = _OllamaStub(
            response='```json {"insight_text":"Great work","category":"unknown","confidence":"2.4"} ```'
        )

        out = insights.run(
            user_id=user_id,
            entry_id=entry_id,
            canonical_text="Read 10 pages",
            rag_hits=[
                {
                    "payload": {
                        "content": "Spaced review improves long-term retention.",
                        "doc_id": "doc-1",
                        "metadata": {"chunk_id": "chunk-1", "title": "Study guide"},
                    }
                }
            ],
            detection={"task_type": "learning", "detected_skills": []},
            ollama_health={"connected": True},
            ollama=ollama,
            db=db,
        )

        assert out["insight_text"] == "Great work"
        assert out["insight_category"] == "general"
        assert out["insight_confidence"] == 1.0
        assert out["from_ollama"] is True
        assert out["from_cache"] is False
        assert out["generated"] is True


def test_insights_cache_hit_avoids_second_ollama_call_but_writes_new_db_rows() -> None:
    with _make_db() as db:
        user_id, entry_id = _seed_user_and_entry(db)
        ollama = _OllamaStub(
            response='{"insight_text":"Keep shipping","category":"mindset","confidence":0.8}'
        )
        cache = StepCache()
        rag_hits = [{"payload": {"content": "Consistency helps"}}]
        detection = {"task_type": "practice", "detected_skills": ["Python"]}

        out_1 = insights.run(
            user_id=user_id,
            entry_id=entry_id,
            canonical_text="Built a feature",
            rag_hits=rag_hits,
            detection=detection,
            ollama_health={"connected": True},
            ollama=ollama,
            db=db,
            cache=cache,
        )
        out_2 = insights.run(
            user_id=user_id,
            entry_id=entry_id,
            canonical_text="Built a feature",
            rag_hits=rag_hits,
            detection=detection,
            ollama_health={"connected": True},
            ollama=ollama,
            db=db,
            cache=cache,
        )

        assert out_1["from_cache"] is False
        assert out_2["from_cache"] is True
        assert out_2["from_ollama"] is True
        assert ollama.calls == 1
        assert db.query(Insight).count() == 2
        assert db.query(InsightEvidence).count() == 2
