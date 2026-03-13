"""Personality RAG retrieval built on the shared runtime-configured Qdrant client."""

from __future__ import annotations

import logging
from typing import Any

from src.ai.qdrant import QdrantClient

logger = logging.getLogger(__name__)


def _to_citation(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata") or {}
    return {
        "doc_id": result.get("doc_id"),
        "chunk_id": metadata.get("chunk_id"),
        "title": metadata.get("title") or result.get("source") or metadata.get("source"),
        "source_type": metadata.get("source_type") or result.get("category") or "rag_document",
        "locator": metadata.get("locator"),
        "retrieved_at_utc": metadata.get("retrieved_at_utc"),
    }


class PersonalityRAGService:
    """RAG retrieval for personality context and safety resources."""

    def __init__(self, client: QdrantClient | None = None) -> None:
        self.client = client or QdrantClient()

    def retrieve_relevant_context(
        self,
        query_text: str,
        user_id: str,
        personality: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        del user_id  # Reserved for future user-scoped filtering.
        if not query_text.strip():
            return []

        try:
            results = self.client.search(query_text, limit=limit)
        except Exception as exc:
            logger.warning("Personality RAG retrieval failed: %s", exc)
            return []

        output: list[dict[str, Any]] = []
        for result in results:
            metadata = {
                "category": result.get("category"),
                "source": result.get("source"),
                "tags": result.get("tags", []),
                "personality": personality,
            }
            output.append(
                {
                    "content": result.get("content", ""),
                    "metadata": metadata,
                    "score": result.get("score", 0.0),
                    "citation": _to_citation(result),
                }
            )
        return output

    def retrieve_safety_resources(
        self,
        user_id: str,
        country: str = "FR",
    ) -> list[dict[str, Any]]:
        del user_id
        query = f"crisis safety support resources {country}"
        try:
            results = self.client.search(query, limit=10)
        except Exception as exc:
            logger.warning("Personality safety retrieval failed: %s", exc)
            return []

        resources: list[dict[str, Any]] = []
        for result in results:
            category = (result.get("category") or "").lower()
            if category and "safety" not in category and "crisis" not in category:
                continue
            resources.append(
                {
                    "content": result.get("content", ""),
                    "metadata": {
                        "category": result.get("category"),
                        "source": result.get("source"),
                        "tags": result.get("tags", []),
                    },
                }
            )
        return resources
