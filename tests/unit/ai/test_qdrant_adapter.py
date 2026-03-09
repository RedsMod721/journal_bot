"""Unit tests for src.ai.qdrant."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import src.ai.qdrant as qdrant_module


class _DummyDistance:
    COSINE = "cosine"


class _DummyVectorParams:
    def __init__(self, size: int, distance: str) -> None:
        self.size = size
        self.distance = distance


class _DummyPointStruct:
    def __init__(self, id, vector, payload) -> None:
        self.id = id
        self.vector = vector
        self.payload = payload


class _DummyQdrantClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.collection_names: list[str] = []
        self.created: list[dict] = []
        self.upserts: list[dict] = []
        self.search_rows = [SimpleNamespace(id="p1", score=0.99, payload={"k": "v"})]

    def get_collections(self):
        rows = [SimpleNamespace(name=name) for name in self.collection_names]
        return SimpleNamespace(collections=rows)

    def create_collection(self, **kwargs) -> None:
        self.created.append(kwargs)
        self.collection_names.append(kwargs["collection_name"])

    def upsert(self, **kwargs) -> None:
        self.upserts.append(kwargs)

    def search(self, **kwargs):
        return self.search_rows


@pytest.fixture(autouse=True)
def _patch_qdrant_primitives(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(qdrant_module, "_QdrantClientLib", _DummyQdrantClient)
    monkeypatch.setattr(qdrant_module, "Distance", _DummyDistance)
    monkeypatch.setattr(qdrant_module, "VectorParams", _DummyVectorParams)
    monkeypatch.setattr(qdrant_module, "PointStruct", _DummyPointStruct)
    monkeypatch.setattr(
        qdrant_module,
        "get_qdrant_defaults",
        lambda: {
            "host": "localhost",
            "port": 6333,
            "collection": "rag_documents",
            "vector_size": 384,
            "mode": "remote",
            "local_path": str(tmp_path / "qdrant_local"),
        },
    )


def test_init_remote_mode_uses_host_and_port() -> None:
    adapter = qdrant_module.QdrantClientAdapter()
    assert adapter.client.kwargs == {"host": "localhost", "port": 6333}


def test_init_local_mode_creates_local_path(tmp_path: Path) -> None:
    local_path = tmp_path / "nested" / "qdrant"
    adapter = qdrant_module.QdrantClientAdapter(mode="local", local_path=local_path)
    assert local_path.exists()
    assert adapter.client.kwargs == {"path": str(local_path)}


def test_init_invalid_mode_raises_value_error() -> None:
    with pytest.raises(ValueError):
        qdrant_module.QdrantClientAdapter(mode="invalid")


def test_ensure_collection_creates_when_missing() -> None:
    adapter = qdrant_module.QdrantClientAdapter()
    adapter.ensure_collection()

    assert len(adapter.client.created) == 1
    created = adapter.client.created[0]
    assert created["collection_name"] == "rag_documents"
    assert created["vectors_config"].size == 384
    assert created["vectors_config"].distance == _DummyDistance.COSINE


def test_ensure_collection_noop_when_present() -> None:
    adapter = qdrant_module.QdrantClientAdapter()
    adapter.client.collection_names = ["rag_documents"]

    adapter.ensure_collection()

    assert adapter.client.created == []


def test_normalize_point_id_branches() -> None:
    assert qdrant_module.QdrantClientAdapter._normalize_point_id(7) == 7
    uuid_text = "123e4567-e89b-12d3-a456-426614174000"
    assert qdrant_module.QdrantClientAdapter._normalize_point_id(uuid_text) == uuid_text
    hashed = qdrant_module.QdrantClientAdapter._normalize_point_id("semantic-id")
    assert isinstance(hashed, str)
    with pytest.raises(ValueError):
        qdrant_module.QdrantClientAdapter._normalize_point_id("   ")


def test_upsert_documents_writes_source_point_id_payload() -> None:
    adapter = qdrant_module.QdrantClientAdapter()
    adapter.upsert_documents(
        [
            {
                "point_id": "doc-1",
                "vector": [0.1, 0.2],
                "payload": {"title": "Doc"},
            }
        ]
    )

    assert len(adapter.client.upserts) == 1
    points = adapter.client.upserts[0]["points"]
    assert len(points) == 1
    assert points[0].payload["source_point_id"] == "doc-1"


def test_upsert_documents_noop_for_empty_input() -> None:
    adapter = qdrant_module.QdrantClientAdapter()
    adapter.upsert_documents([])
    assert adapter.client.upserts == []


def test_search_maps_qdrant_rows_to_dicts() -> None:
    adapter = qdrant_module.QdrantClientAdapter()
    out = adapter.search([0.0, 0.1], limit=3)
    assert out == [{"point_id": "p1", "score": 0.99, "payload": {"k": "v"}}]
