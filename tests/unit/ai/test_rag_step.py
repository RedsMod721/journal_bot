"""Unit tests for src.ai.steps.rag."""

from __future__ import annotations

# ruff: noqa: E402

import sys
import types

_stub = types.ModuleType("sentence_transformers")
_stub.SentenceTransformer = object  # type: ignore[attr-defined]
sys.modules.setdefault("sentence_transformers", _stub)

from src.ai.cache import StepCache  # noqa: E402
from src.ai.steps import rag  # noqa: E402


class _QdrantStub:
    def __init__(self) -> None:
        self.ensure_calls = 0
        self.search_calls = 0

    def ensure_collection(self) -> None:
        self.ensure_calls += 1

    def search(self, _vector, limit=5):
        self.search_calls += 1
        return [{"point_id": "p1"}, {"point_id": "p2"}][:limit]


def test_rag_cache_miss_writes_cache_and_returns_from_cache_false() -> None:
    qdrant = _QdrantStub()
    cache = StepCache()

    out = rag.run(vector=[0.1, 0.2], qdrant=qdrant, cache=cache, entry_id="e1")

    assert out["hit_count"] == 2
    assert out["fallback"] is False
    assert out["from_cache"] is False
    assert qdrant.ensure_calls == 1
    assert qdrant.search_calls == 1
    assert cache.get("rag:e1") == {
        "hits": out["hits"],
        "hit_count": 2,
        "fallback": False,
    }


def test_rag_cache_hit_skips_qdrant_calls() -> None:
    qdrant = _QdrantStub()
    cache = StepCache()
    cache.set(
        "rag:e2", {"hits": [{"point_id": "cached"}], "hit_count": 1, "fallback": False}
    )

    out = rag.run(vector=[0.4], qdrant=qdrant, cache=cache, entry_id="e2")

    assert out == {
        "hits": [{"point_id": "cached"}],
        "hit_count": 1,
        "fallback": False,
        "from_cache": True,
    }
    assert qdrant.ensure_calls == 0
    assert qdrant.search_calls == 0


def test_rag_without_entry_id_does_not_use_cache() -> None:
    qdrant = _QdrantStub()
    cache = StepCache()

    out = rag.run(vector=[0.5], qdrant=qdrant, cache=cache, entry_id="")

    assert out["from_cache"] is False
    assert qdrant.ensure_calls == 1
    assert qdrant.search_calls == 1
    assert cache.get_stats()["size"] == 0
