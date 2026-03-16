"""RAG (Retrieval-Augmented Generation) package for global knowledge base.

Implements Section 11.4 (RAG: global KB) from architecture.
"""

from src.ai.rag.rag_service import (
    RAGService,
    _chunk_text,
    _make_chunk_id,
    _make_point_id,
    _normalize_text,
    RAG_GLOBAL_KB_NAMESPACE_UUID,
)

__all__ = [
    "RAGService",
    "RAG_GLOBAL_KB_NAMESPACE_UUID",
    "_normalize_text",
    "_chunk_text",
    "_make_chunk_id",
    "_make_point_id",
]
