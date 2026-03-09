"""Unit tests for src.ai.cache."""

from __future__ import annotations

import pytest

from src.ai.cache import StepCache


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
