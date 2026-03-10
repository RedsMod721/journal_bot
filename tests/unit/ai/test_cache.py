"""Unit tests for src.ai.cache."""

from __future__ import annotations

# ruff: noqa: E402

import hashlib
import sys
import types

import pytest

# Avoid importing heavyweight sentence-transformers/torch during src.ai package import.
_stub = types.ModuleType("sentence_transformers")
_stub.SentenceTransformer = object  # type: ignore[attr-defined]
sys.modules.setdefault("sentence_transformers", _stub)

from src.ai.cache import PipelineCache, StepCache  # noqa: E402


def test_step_cache_set_get_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    now = {"t": 1000.0}

    def _time() -> float:
        return now["t"]

    monkeypatch.setattr("src.ai.cache.time.time", _time)

    cache = StepCache(ttl_hours=1)
    cache.set("k", {"value": 1})

    assert cache.get("k") == {"value": 1}
    now["t"] = 1000.0 + 3600.0
    assert cache.get("k") is None
    assert cache.get("missing") is None


def test_step_cache_lru_eviction_and_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    now = {"t": 2000.0}

    def _time() -> float:
        return now["t"]

    monkeypatch.setattr("src.ai.cache.time.time", _time)

    cache = StepCache(ttl_hours=1, max_size=2)
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1  # promote "a" to MRU; "b" becomes LRU
    cache.set("c", 3)  # evicts "b"

    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3

    stats = cache.get_stats()
    assert stats["hits"] == 3
    assert stats["misses"] == 1
    assert stats["evictions"] == 1
    assert stats["size"] == 2
    assert stats["max_size"] == 2
    assert stats["hit_rate"] == pytest.approx(0.75)


def test_step_cache_updating_existing_key_does_not_evict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = {"t": 3000.0}

    def _time() -> float:
        return now["t"]

    monkeypatch.setattr("src.ai.cache.time.time", _time)

    cache = StepCache(ttl_hours=1, max_size=1)
    cache.set("a", 1)
    cache.set("a", 2)

    assert cache.get("a") == 2
    assert cache.get_stats()["evictions"] == 0


def test_step_cache_clear_resets_store_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = {"t": 4000.0}

    def _time() -> float:
        return now["t"]

    monkeypatch.setattr("src.ai.cache.time.time", _time)

    cache = StepCache(ttl_hours=1, max_size=2)
    cache.set("x", 1)
    assert cache.get("x") == 1
    assert cache.get("missing") is None

    cache.clear()
    assert cache.get("x") is None
    stats = cache.get_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 1
    assert stats["evictions"] == 0
    assert stats["size"] == 0
    assert stats["hit_rate"] == 0.0


def test_hash_key_is_stable_and_16_chars() -> None:
    expected = hashlib.sha256("hello".encode()).hexdigest()[:16]
    assert StepCache.hash_key("hello") == expected
    assert len(StepCache.hash_key("hello")) == 16
    assert StepCache.hash_key("hello") == StepCache.hash_key("hello")


def test_pipeline_cache_alias_points_to_step_cache() -> None:
    cache = PipelineCache(ttl_hours=1)
    assert isinstance(cache, StepCache)
