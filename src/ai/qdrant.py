"""Qdrant adapter for RAG retrieval."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from src.ai.runtime_config import get_qdrant_defaults

QdrantClient: Any = None
Distance: Any = None
PointStruct: Any = None
VectorParams: Any = None

try:
    from qdrant_client import QdrantClient as _QdrantClient
    from qdrant_client.models import (
        Distance as _Distance,
        PointStruct as _PointStruct,
        VectorParams as _VectorParams,
    )

    QdrantClient = _QdrantClient
    Distance = _Distance
    PointStruct = _PointStruct
    VectorParams = _VectorParams
except Exception:  # pragma: no cover - optional dependency fallback
    pass


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
        if QdrantClient is None:
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

        if self.mode == "local":
            self.local_path.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(self.local_path))
            return

        if self.mode != "remote":
            raise ValueError("Qdrant mode must be 'remote' or 'local'")

        self.client = QdrantClient(host=self.host, port=self.port)

    def ensure_collection(self) -> None:
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
