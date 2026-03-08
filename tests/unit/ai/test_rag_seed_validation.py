"""Optional seeded-RAG validation tests (enabled only when explicitly requested)."""

from __future__ import annotations

import os

import pytest

from src.ai.ollama import OllamaClient
from src.ai.qdrant import QdrantClientAdapter


def _enabled() -> bool:
    return os.getenv("RUN_SEEDED_RAG_TEST", "0") == "1"


@pytest.mark.skipif(
    not _enabled(), reason="set RUN_SEEDED_RAG_TEST=1 after seed window B"
)
def test_seeded_rag_returns_hits_for_known_query():
    ollama = OllamaClient()
    qdrant = QdrantClientAdapter()

    health = ollama.health()
    assert health.get("connected") is True

    qdrant.ensure_collection()
    vector = ollama.embed("habit formation and deliberate practice")
    hits = qdrant.search(vector, limit=5)

    assert isinstance(hits, list)
    assert len(hits) > 0
    assert all("payload" in h for h in hits)
