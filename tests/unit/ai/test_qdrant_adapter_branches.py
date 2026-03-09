"""Additional branch tests for src.ai.qdrant."""

from __future__ import annotations

import pytest

import src.ai.qdrant as qdrant_module


def test_constructor_raises_when_qdrant_client_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(qdrant_module, "_QdrantClientLib", None)
    with pytest.raises(RuntimeError, match="qdrant-client is not installed"):
        qdrant_module.QdrantClientAdapter()


def test_normalize_point_id_maps_arbitrary_text_to_uuid() -> None:
    out = qdrant_module.QdrantClientAdapter._normalize_point_id("semantic::doc::id")
    assert isinstance(out, str)
    assert len(out) == 36
