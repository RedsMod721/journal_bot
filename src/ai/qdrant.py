"""Qdrant adapter for RAG retrieval."""

from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from loguru import logger

# Inject the Windows system certificate store (includes corporate CAs) so that
# requests to HuggingFace Hub succeed in environments that use TLS inspection.
try:
    import truststore  # type: ignore[import-untyped]
    truststore.inject_into_ssl()
except Exception:  # pragma: no cover - optional on non-Windows or absent install
    pass

from src.ai.runtime_config import get_qdrant_defaults
from src.ai.tx_guard import assert_network_allowed

_QdrantClientLib: Any = None
Distance: Any = None
PointStruct: Any = None
VectorParams: Any = None

try:
    from qdrant_client import QdrantClient as _QdrantClientLib_
    from qdrant_client.models import (
        Distance as _Distance,
        PointStruct as _PointStruct,
        VectorParams as _VectorParams,
    )

    _QdrantClientLib = _QdrantClientLib_
    Distance = _Distance
    PointStruct = _PointStruct
    VectorParams = _VectorParams
except Exception:  # pragma: no cover - optional dependency fallback
    pass

_SentenceTransformerLib: Any = None
_SharedEmbeddingModel: Any = None
_LOCAL_EMBEDDED_CLIENTS: dict[str, Any] = {}


def _sentence_transformers_enabled() -> bool:
    """Return whether sentence-transformers loading is enabled.

    The embedding stack is opt-in because first-time model loading may require
    heavyweight imports and local model artifacts. Set
    ``ENABLE_SENTENCE_TRANSFORMERS=1`` to enable semantic search.
    """
    raw = os.getenv("ENABLE_SENTENCE_TRANSFORMERS")
    if raw is None:
        defaults = get_qdrant_defaults()
        return bool(defaults.get("enable_sentence_transformers", False))
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _sentence_transformers_allow_download() -> bool:
    """Return whether model downloads are allowed during runtime loading."""
    raw = os.getenv("SENTENCE_TRANSFORMERS_ALLOW_DOWNLOAD")
    if raw is None:
        defaults = get_qdrant_defaults()
        return bool(defaults.get("allow_sentence_transformers_download", False))
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def _temporary_env(overrides: dict[str, str]) -> Any:
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        os.environ.update(overrides)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _load_sentence_transformer_lib() -> Any:
    """Return SentenceTransformer class if available, else ``None``.

    Imported lazily to avoid heavy optional dependency loading at module
    import time.
    """
    global _SentenceTransformerLib
    if _SentenceTransformerLib is not None:
        return _SentenceTransformerLib
    if not _sentence_transformers_enabled():
        _SentenceTransformerLib = None
        return None
    if (
        "sentence_transformers" not in sys.modules
        and importlib.util.find_spec("sentence_transformers") is None
    ):
        _SentenceTransformerLib = None
        return None
    try:
        from sentence_transformers import SentenceTransformer as _SentenceTransformer  # type: ignore[import-untyped]

        _SentenceTransformerLib = _SentenceTransformer
    except Exception:  # pragma: no cover - optional dependency fallback
        _SentenceTransformerLib = None
    return _SentenceTransformerLib


def _load_sentence_transformer_model(
    sentence_transformer_lib: Any,
    model_name: str,
) -> Any:
    """Instantiate a sentence-transformers model with local-cache-first semantics."""
    kwargs: dict[str, Any] = {}
    env_overrides: dict[str, str] = {}
    if not _sentence_transformers_allow_download():
        kwargs["local_files_only"] = True
        env_overrides = {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }

    with _temporary_env(env_overrides):
        try:
            return sentence_transformer_lib(model_name, **kwargs)
        except TypeError:
            # Older tests/fakes accept only the model name.
            return sentence_transformer_lib(model_name)


# all-mpnet-base-v2 produces 768-dimensional vectors.
_EMBEDDING_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"
_EMBEDDING_VECTOR_SIZE = 768


def _get_shared_embedding_model() -> Any:
    """Return the shared sentence-transformers model instance, if available."""
    global _SharedEmbeddingModel
    if _SharedEmbeddingModel is not None:
        return _SharedEmbeddingModel

    if not _sentence_transformers_enabled():
        logger.info(
            "sentence-transformers loading is disabled; set "
            "ENABLE_SENTENCE_TRANSFORMERS=1 to enable semantic search."
        )
        return None

    sentence_transformer_lib = _SentenceTransformerLib or _load_sentence_transformer_lib()
    if sentence_transformer_lib is None:  # pragma: no cover
        logger.warning(
            "sentence-transformers could not be imported; semantic search "
            "will remain unavailable."
        )
        return None

    try:
        logger.info("Loading embedding model: {}", _EMBEDDING_MODEL_NAME)
        _SharedEmbeddingModel = _load_sentence_transformer_model(
            sentence_transformer_lib,
            _EMBEDDING_MODEL_NAME,
        )
    except Exception as exc:
        logger.warning(
            "Failed to load embedding model '{}': {}. "
            "Semantic search will remain unavailable until the model is "
            "available locally or downloads are enabled via "
            "SENTENCE_TRANSFORMERS_ALLOW_DOWNLOAD=1.",
            _EMBEDDING_MODEL_NAME,
            exc,
        )
        _SharedEmbeddingModel = None

    return _SharedEmbeddingModel


class QdrantClientAdapter:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection: str | None = None,
        vector_size: int | None = None,
        mode: str | None = None,
        local_path: str | Path | None = None,
    ) -> None:
        if _QdrantClientLib is None:
            raise RuntimeError(
                "qdrant-client is not installed. Install requirements.txt to use Qdrant."
            )
        defaults = get_qdrant_defaults()
        self.mode = (mode or defaults["mode"]).lower()
        self.host = host or defaults["host"]
        self.port = int(port if port is not None else defaults["port"])
        self.collection = collection or defaults["collection"]
        self.vector_size = int(
            vector_size if vector_size is not None else defaults["vector_size"]
        )
        self.local_path = Path(
            str(local_path) if local_path is not None else defaults["local_path"]
        )
        self.embedding_model = _get_shared_embedding_model()

        if self.mode == "local":
            self.local_path.mkdir(parents=True, exist_ok=True)
            client_key = str(self.local_path.resolve())
            cached = _LOCAL_EMBEDDED_CLIENTS.get(client_key)
            if cached is None:
                cached = _QdrantClientLib(path=str(self.local_path))
                _LOCAL_EMBEDDED_CLIENTS[client_key] = cached
            self.client = cached
            return

        if self.mode != "remote":
            raise ValueError("Qdrant mode must be 'remote' or 'local'")

        self.client = _QdrantClientLib(host=self.host, port=self.port)

    def ensure_collection(self) -> None:
        assert_network_allowed("qdrant.ensure_collection")
        collections = self.client.get_collections().collections
        if any(c.name == self.collection for c in collections):
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(
                size=self.vector_size, distance=Distance.COSINE
            ),
        )

    @staticmethod
    def _normalize_point_id(raw_id: Any) -> int | str:
        if isinstance(raw_id, int):
            return raw_id

        text = str(raw_id).strip()
        if not text:
            raise ValueError("point_id must not be empty")

        try:
            return str(uuid.UUID(text))
        except ValueError:
            # Qdrant IDs must be uint64 or UUID; map arbitrary semantic IDs to UUIDv5.
            return str(uuid.uuid5(uuid.NAMESPACE_URL, text))

    def upsert_documents(self, docs: list[dict[str, Any]]) -> None:
        assert_network_allowed("qdrant.upsert_documents")
        points = [
            PointStruct(
                id=self._normalize_point_id(doc["point_id"]),
                vector=doc["vector"],
                payload={
                    **(doc.get("payload", {}) or {}),
                    "source_point_id": str(doc.get("point_id")),
                },
            )
            for doc in docs
        ]
        if not points:
            return
        self.client.upsert(collection_name=self.collection, points=points)

    def search(self, vector: list[float], limit: int = 5) -> list[dict[str, Any]]:
        assert_network_allowed("qdrant.search")
        results = self.client.search(
            collection_name=self.collection, query_vector=vector, limit=limit
        )
        return [
            {
                "point_id": r.id,
                "score": r.score,
                "payload": r.payload,
            }
            for r in results
        ]

    def encode_text(self, text: str) -> list[float]:
        """Encode *text* with the shared RAG embedding model."""
        if self.embedding_model is None:
            raise RuntimeError("Embedding model unavailable")
        vector = self.embedding_model.encode(text)
        return vector.tolist()

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Encode a list of texts in one batched call (faster than looping encode_text)."""
        if self.embedding_model is None:
            raise RuntimeError("Embedding model unavailable")
        vectors = self.embedding_model.encode(texts)
        return [v.tolist() for v in vectors]


class QdrantClient:
    """High-level Qdrant client with natural-language semantic search.

    Wraps :class:`QdrantClientAdapter` and adds an embedding step so
    callers can query by raw text rather than pre-computed vectors.
    The sentence-transformers model is loaded once and reused across
    all calls (expensive to initialise).
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection: str | None = None,
        vector_size: int | None = None,
        mode: str | None = None,
        local_path: str | Path | None = None,
    ) -> None:
        """Initialise the client.

        All parameters are optional; missing values are resolved from
        the runtime configuration (``config/dev.yaml`` or environment
        variables).

        Args:
            host: Qdrant server hostname (remote mode only).
            port: Qdrant server port (remote mode only).
            collection: Target collection name.
            vector_size: Expected vector dimension (used when creating a
                new collection).  Defaults to the config value; a warning
                is emitted if it does not match the embedding model's
                actual output dimension (:data:`_EMBEDDING_VECTOR_SIZE`).
            mode: ``"remote"`` (default) or ``"local"`` (embedded Qdrant).
            local_path: Filesystem path for local-mode storage.
        """
        self._adapter = QdrantClientAdapter(
            host=host,
            port=port,
            collection=collection,
            vector_size=vector_size,
            mode=mode,
            local_path=local_path,
        )
        self.host = self._adapter.host
        self.port = self._adapter.port
        self.collection = self._adapter.collection
        self.vector_size = self._adapter.vector_size
        self.embedding_model = self._adapter.embedding_model

        if self.vector_size != _EMBEDDING_VECTOR_SIZE:
            logger.warning(
                "Config vector_size={} does not match embedding model output "
                "size={} ({}). Collection will be created with the model's "
                "actual dimension ({}).",
                self.vector_size,
                _EMBEDDING_VECTOR_SIZE,
                _EMBEDDING_MODEL_NAME,
                _EMBEDDING_VECTOR_SIZE,
            )
            self.vector_size = _EMBEDDING_VECTOR_SIZE
            self._adapter.vector_size = _EMBEDDING_VECTOR_SIZE

        logger.info(
            "QdrantClient ready — {}:{}, collection='{}', vector_size={}",
            self.host,
            self.port,
            self.collection,
            self.vector_size,
        )

    # ------------------------------------------------------------------
    # Health / collection management
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return ``True`` if the Qdrant service responds to a health probe.

        Attempts up to 3 times before giving up.

        Returns:
            ``True`` if the service is reachable, ``False`` otherwise.
        """
        for attempt in range(1, 4):
            try:
                self._adapter.client.get_collections()
                return True
            except Exception as exc:
                logger.warning(
                    "Qdrant availability check attempt {}/3 failed: {}", attempt, exc
                )
        return False

    def collection_exists(self) -> bool:
        """Return ``True`` if the configured collection is present in Qdrant.

        Returns:
            ``True`` if the collection exists, ``False`` on absence *or*
            any connection error.
        """
        try:
            collections = self._adapter.client.get_collections().collections
            return any(c.name == self.collection for c in collections)
        except Exception as exc:
            logger.warning("Could not check collection existence: {}", exc)
            return False

    def create_collection(self) -> None:
        """Create the RAG documents collection.

        Uses :data:`_EMBEDDING_VECTOR_SIZE` (the embedding model's actual
        output dimension) and Cosine distance.  Silently no-ops and logs a
        warning if the required Qdrant primitives are unavailable.
        """
        if VectorParams is None or Distance is None:  # pragma: no cover
            logger.warning("Qdrant primitives unavailable; cannot create collection.")
            return
        try:
            self._adapter.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=_EMBEDDING_VECTOR_SIZE, distance=Distance.COSINE
                ),
            )
            logger.info(
                "Created collection '{}' with vector_size={}.",
                self.collection,
                _EMBEDDING_VECTOR_SIZE,
            )
        except Exception as exc:
            logger.warning("Failed to create collection '{}': {}", self.collection, exc)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 5,
        score_threshold: float = 0.70,
    ) -> list[dict[str, Any]]:
        """Semantic search over RAG documents.

        Converts *query* to an embedding vector and performs an
        approximate-nearest-neighbour search against the Qdrant collection.
        Results below *score_threshold* are discarded.

        Retries up to 3 times on transient errors; returns ``[]`` on any
        unrecoverable failure so the pipeline can continue without RAG
        context.

        Args:
            query: Natural-language query text (e.g. a journal entry summary).
            limit: Maximum number of results to return before score filtering.
            score_threshold: Minimum cosine similarity score (0–1).  Results
                with a score below this value are excluded.

        Returns:
            List of matching document dicts, each containing:
            ``doc_id``, ``content``, ``category``, ``score``, ``source``,
            ``tags``, ``confidence``.  Empty list on error or no matches.
        """
        if not query or not query.strip():
            logger.warning("Empty query passed to search(); returning [].")
            return []

        if self.embedding_model is None:  # pragma: no cover
            logger.debug("Embedding model unavailable; skipping semantic search.")
            return []

        try:
            vector = self._encode_query(query)
        except Exception as exc:
            logger.warning("Failed to encode query: {}", exc)
            return []

        if not self.collection_exists():
            logger.info(
                "Collection '{}' missing before search; creating it now.",
                self.collection,
            )
            self.create_collection()

        for attempt in range(1, 4):
            try:
                raw = self._adapter.search(vector, limit=limit)

                results: list[dict[str, Any]] = []
                for item in raw:
                    if item["score"] < score_threshold:
                        continue
                    payload: dict[str, Any] = item.get("payload") or {}
                    results.append(
                        {
                            "doc_id": payload.get("doc_id", str(item["point_id"])),
                            "content": payload.get("content", ""),
                            "category": payload.get("category", ""),
                            "score": item["score"],
                            "source": payload.get("source", ""),
                            "tags": payload.get("tags", []),
                            "confidence": payload.get("confidence"),
                        }
                    )

                logger.debug(
                    "RAG search for '{}' → {} result(s) above threshold {:.2f}.",
                    query[:60],
                    len(results),
                    score_threshold,
                )
                return results

            except Exception as exc:
                logger.warning("Search attempt {}/3 failed: {}", attempt, exc)

        logger.warning(
            "All search attempts exhausted for query '{}'; returning [].",
            query[:60],
        )
        return []

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def count_documents(self) -> int:
        """Return the number of documents stored in the collection.

        Returns:
            Document count, or ``0`` if the collection doesn't exist or
            any error occurs.
        """
        try:
            result = self._adapter.client.count(collection_name=self.collection)
            return result.count
        except Exception as exc:
            logger.warning(
                "Could not count documents in '{}': {}", self.collection, exc
            )
            return 0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _encode_query(self, text: str) -> list[float]:
        """Encode *text* into an embedding vector.

        The model is loaded once in :meth:`__init__` and reused here.

        Args:
            text: Query string to embed.

        Returns:
            Embedding as a plain Python ``list[float]`` (not a NumPy array).
        """
        if self.embedding_model is None:
            raise RuntimeError("Embedding model unavailable")
        vector = self.embedding_model.encode(text)
        # sentence-transformers returns a numpy array; convert for Qdrant.
        return vector.tolist()
