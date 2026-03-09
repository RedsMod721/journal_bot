"""High-level branch tests for src.ai.qdrant.QdrantClient."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.ai.qdrant as qdrant_module


class _FakeDistance:
    COSINE = "cosine"


class _FakeVectorParams:
    def __init__(self, size: int, distance: str) -> None:
        self.size = size
        self.distance = distance


class _FakeEmbeddingVector:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return list(self._values)


class _FakeEmbeddingModel:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def encode(self, text: str) -> _FakeEmbeddingVector:
        assert isinstance(text, str)
        return _FakeEmbeddingVector([0.11, 0.22, 0.33])


class _FakeSentenceTransformer:
    def __init__(self, model_name: str) -> None:
        self._model = _FakeEmbeddingModel(model_name)

    def encode(self, text: str) -> _FakeEmbeddingVector:
        return self._model.encode(text)


class _FakeBackendClient:
    def __init__(self) -> None:
        self.collection_names: list[str] = []
        self.created: list[dict] = []
        self.count_value = 0
        self.fail_get_collections_times = 0
        self.fail_create = False
        self.fail_count = False

    def get_collections(self):
        if self.fail_get_collections_times > 0:
            self.fail_get_collections_times -= 1
            raise RuntimeError("collections down")
        return SimpleNamespace(
            collections=[SimpleNamespace(name=name) for name in self.collection_names]
        )

    def create_collection(self, **kwargs) -> None:
        if self.fail_create:
            raise RuntimeError("create failed")
        self.created.append(kwargs)
        self.collection_names.append(kwargs["collection_name"])

    def count(self, *, collection_name: str):
        if self.fail_count:
            raise RuntimeError("count failed")
        return SimpleNamespace(count=self.count_value)


class _FakeAdapter:
    backend = _FakeBackendClient()
    raw_results: list[dict] = []
    fail_search_times = 0

    def __init__(
        self,
        host=None,
        port=None,
        collection=None,
        vector_size=None,
        mode=None,
        local_path=None,
    ) -> None:
        self.host = host or "localhost"
        self.port = int(port if port is not None else 6333)
        self.collection = collection or "rag_documents"
        self.vector_size = int(vector_size if vector_size is not None else 3072)
        self.client = _FakeAdapter.backend

    def search(self, vector: list[float], limit: int = 5) -> list[dict]:
        assert isinstance(vector, list)
        if _FakeAdapter.fail_search_times > 0:
            _FakeAdapter.fail_search_times -= 1
            raise RuntimeError("search failed")
        return _FakeAdapter.raw_results[:limit]


@pytest.fixture(autouse=True)
def _patch_high_level_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeAdapter.backend = _FakeBackendClient()
    _FakeAdapter.raw_results = []
    _FakeAdapter.fail_search_times = 0

    monkeypatch.setattr(qdrant_module, "QdrantClientAdapter", _FakeAdapter)
    monkeypatch.setattr(qdrant_module, "_SentenceTransformerLib", _FakeSentenceTransformer)
    monkeypatch.setattr(qdrant_module, "Distance", _FakeDistance)
    monkeypatch.setattr(qdrant_module, "VectorParams", _FakeVectorParams)


def test_init_loads_embedding_and_encode_query() -> None:
    client = qdrant_module.QdrantClient()
    assert client.host == "localhost"
    assert client.port == 6333
    assert client.collection == "rag_documents"
    assert client._encode_query("focus") == [0.11, 0.22, 0.33]


def test_is_available_retries_and_returns_false() -> None:
    client = qdrant_module.QdrantClient()
    _FakeAdapter.backend.fail_get_collections_times = 3
    assert client.is_available() is False


def test_collection_exists_true_false_and_error() -> None:
    client = qdrant_module.QdrantClient()
    _FakeAdapter.backend.collection_names = ["rag_documents"]
    assert client.collection_exists() is True

    _FakeAdapter.backend.collection_names = ["other"]
    assert client.collection_exists() is False

    _FakeAdapter.backend.fail_get_collections_times = 1
    assert client.collection_exists() is False


def test_create_collection_success_and_failure() -> None:
    client = qdrant_module.QdrantClient()

    client.create_collection()
    assert len(_FakeAdapter.backend.created) == 1
    created = _FakeAdapter.backend.created[0]
    assert created["collection_name"] == "rag_documents"
    assert created["vectors_config"].size == 768
    assert created["vectors_config"].distance == _FakeDistance.COSINE

    _FakeAdapter.backend.fail_create = True
    client.create_collection()  # no raise; warning path only


def test_search_empty_query_and_unavailable_model_return_empty() -> None:
    client = qdrant_module.QdrantClient()
    assert client.search("   ") == []

    client.embedding_model = None
    assert client.search("deliberate practice") == []


def test_search_formats_filters_auto_creates_and_retries() -> None:
    client = qdrant_module.QdrantClient()
    _FakeAdapter.backend.collection_names = []
    _FakeAdapter.fail_search_times = 1
    _FakeAdapter.raw_results = [
        {
            "point_id": "p-low",
            "score": 0.2,
            "payload": {"doc_id": "insight_low", "content": "low"},
        },
        {
            "point_id": "p1",
            "score": 0.91,
            "payload": {
                "doc_id": "insight_001",
                "content": "Deliberate practice requires immediate feedback",
                "category": "learning_science",
                "source": "Ericsson et al. (1993)",
                "tags": ["feedback", "practice"],
                "confidence": 0.95,
            },
        },
    ]

    out = client.search("practice feedback", limit=5, score_threshold=0.70)
    assert len(out) == 1
    assert out[0]["doc_id"] == "insight_001"
    assert out[0]["category"] == "learning_science"
    assert out[0]["score"] == 0.91
    assert _FakeAdapter.backend.collection_names == ["rag_documents"]


def test_search_returns_empty_on_encode_error_and_retry_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    client = qdrant_module.QdrantClient()

    def _boom(_text: str) -> list[float]:
        raise RuntimeError("encode failed")

    monkeypatch.setattr(client, "_encode_query", _boom)
    assert client.search("query") == []

    client2 = qdrant_module.QdrantClient()
    _FakeAdapter.fail_search_times = 3
    assert client2.search("query") == []


def test_count_documents_success_and_error() -> None:
    client = qdrant_module.QdrantClient()
    _FakeAdapter.backend.count_value = 1250
    assert client.count_documents() == 1250

    _FakeAdapter.backend.fail_count = True
    assert client.count_documents() == 0
