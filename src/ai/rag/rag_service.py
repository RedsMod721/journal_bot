"""RAG service for global knowledge base retrieval.

Implements Section 11.4 (RAG: global KB) from architecture.

Design notes
------------
- ``RagDocument`` rows are **per-chunk** (one DB row per chunk).
  ``source_document_id`` stores the canonical ``chunk_id`` string so each
  chunk is individually addressable.
- Chunk text lives only in the DB (``RagDocument.body_text``).
  The Qdrant payload intentionally omits raw text (Section 11.4.5 MUST NOT
  store raw chunk text in Qdrant payload for ``rag_global_kb``).
- ``rag_document_id`` is a 32-hex string (``uuid4().hex``) that groups all
  chunks belonging to one logical document; it is NOT the DB primary key of
  any single row.
- ``chunk_id = "{rag_document_id}#chunk:{chunk_index}"`` (no zero-padding).
- ``point_id = UUIDv5(RAG_GLOBAL_KB_NAMESPACE_UUID, chunk_id)`` (Section 11.4.4).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from src.ai.qdrant import (
    QdrantClientAdapter,
    _load_sentence_transformer_lib,
    _load_sentence_transformer_model,
)
from src.db.models.rag import RagDocument

# ---------------------------------------------------------------------------
# Section 11.4.4 — Canonical namespace for UUIDv5 point IDs (MUST)
# Implementations MUST NOT derive the namespace from a text literal.
# ---------------------------------------------------------------------------
RAG_GLOBAL_KB_NAMESPACE_UUID = uuid.UUID("2a9e7c2c-6b79-4d33-9f2d-2b3e3e5c65b4")

# ---------------------------------------------------------------------------
# Chunker metadata (Section 11.4.3.2) — used for config-hash logging
# ---------------------------------------------------------------------------
_CHUNKER_ALGORITHM_ID = "whitespace-v1"
_CHUNKER_VERSION = "1.0"
_TOKENIZER_ID = "whitespace-split"
_TOKENIZER_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Embedding contract (Section 11.4.2)
# ---------------------------------------------------------------------------
_EMBEDDING_MODEL_ID = "sentence-transformers/all-mpnet-base-v2"
_VECTOR_DIMENSION = 768

# ---------------------------------------------------------------------------
# Default chunking config (Section 11.4.3)
# ---------------------------------------------------------------------------
_DEFAULT_CHUNK_SIZE_TOKENS = 512
_DEFAULT_CHUNK_OVERLAP_TOKENS = 50

# ---------------------------------------------------------------------------
# Default retrieval config (Section 11.4.5)
# ---------------------------------------------------------------------------
_DEFAULT_TOP_K = 5
_DEFAULT_MIN_SCORE = 0.70

# Default Qdrant collection name
_DEFAULT_COLLECTION = "rpg_life_tracker_kb"


# ---------------------------------------------------------------------------
# RAGService
# ---------------------------------------------------------------------------


class RAGService:
    """RAG service for global knowledge base retrieval.

    Provides:
    - Document ingestion with deterministic chunking (Section 11.4.3)
    - Embedding generation and Qdrant vector storage (Section 11.4.2)
    - Semantic retrieval with deterministic citation ordering (Section 11.4.5)
    - Canonical UUIDv5 point IDs (Section 11.4.4)
    """

    def __init__(
        self,
        db: Session,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection_name: str = _DEFAULT_COLLECTION,
        chunk_size_tokens: int = _DEFAULT_CHUNK_SIZE_TOKENS,
        chunk_overlap_tokens: int = _DEFAULT_CHUNK_OVERLAP_TOKENS,
        top_k: int = _DEFAULT_TOP_K,
        min_score: float = _DEFAULT_MIN_SCORE,
    ) -> None:
        self.db = db
        self.collection_name = collection_name
        self.chunk_size_tokens = chunk_size_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens
        self.top_k = top_k
        self.min_score = min_score

        # Qdrant adapter (remote mode; Section 11.4.2)
        self._qdrant = QdrantClientAdapter(
            host=qdrant_host,
            port=qdrant_port,
            collection=collection_name,
            vector_size=_VECTOR_DIMENSION,
            mode="remote",
        )
        self._qdrant.ensure_collection()

        # Sentence-transformers embedding model (lazy-loaded, optional)
        self._embedder = None
        st_lib = _load_sentence_transformer_lib()
        if st_lib is not None:
            try:
                self._embedder = _load_sentence_transformer_model(
                    st_lib, _EMBEDDING_MODEL_ID
                )
                logger.info("RAGService: loaded embedding model {}", _EMBEDDING_MODEL_ID)
            except Exception as exc:
                logger.warning("RAGService: failed to load embedding model: {}", exc)

        # Compute and log chunker config hash (Section 11.4.3.2)
        self._chunker_config_hash = self._compute_chunker_config_hash()
        logger.info(
            "RAGService ready — collection={}, chunker_algorithm_id={}, "
            "chunker_version={}, chunker_config_hash={}...",
            collection_name,
            _CHUNKER_ALGORITHM_ID,
            _CHUNKER_VERSION,
            self._chunker_config_hash[:16],
        )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_document(
        self,
        title: str,
        content: str,
        scope: str = "global",
        owner_user_id: str | None = None,
        source_citation: str | None = None,
        categories: list[str] | None = None,
        verified: bool = False,
    ) -> dict[str, Any]:
        """Ingest a document into the global RAG knowledge base.

        Normalizes, chunks, embeds, and stores the document. Each chunk gets
        its own :class:`~src.db.models.rag.RagDocument` row and a Qdrant
        point.  Chunk text is stored in the DB only — **not** in the Qdrant
        payload (Section 11.4.5).

        Args:
            title: Human-readable document title.
            content: Full document text.
            scope: ``"global"`` or ``"user"``; only ``"global"`` is fully
                supported in this spec version.
            owner_user_id: Required for user-scoped documents; ``None`` for
                global KB.
            source_citation: Optional bibliographic citation string.
            categories: Optional list of category labels (stored as JSON).
            verified: ``True`` if the document has been expert-verified.

        Returns:
            ``{"document_id": str, "chunk_count": int, "content_hash": str}``
            where ``document_id`` is a 32-hex string.

        Raises:
            RuntimeError: If the embedding model is unavailable.
        """
        if self._embedder is None:
            raise RuntimeError(
                "Embedding model unavailable; cannot ingest document. "
                "Install sentence-transformers and set ENABLE_SENTENCE_TRANSFORMERS=1."
            )

        # Step 1: Normalize (Section 11.4.3.1)
        normalized = _normalize_text(content)

        # Step 2: Content hash for dedup (SHA-256 of normalized text, 64-hex)
        content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

        # Step 3: Chunk (Section 11.4.3.2)
        chunks = _chunk_text(normalized, self.chunk_size_tokens, self.chunk_overlap_tokens)

        # Step 4: Logical document ID (32-hex, no dashes — matches CitationItem validator)
        document_id = uuid.uuid4().hex

        categories_json = json.dumps(categories) if categories else None

        # Step 5: Embed all chunks in one batch call
        chunk_texts = [c["text"] for c in chunks]
        embeddings = self._embedder.encode(chunk_texts, show_progress_bar=False)

        # Step 6: Build DB rows + Qdrant points
        db_rows: list[RagDocument] = []
        qdrant_points: list[dict[str, Any]] = []

        for chunk, embedding in zip(chunks, embeddings):
            chunk_index: int = chunk["chunk_index"]
            chunk_text: str = chunk["text"]

            chunk_id = _make_chunk_id(document_id, chunk_index)
            point_id = _make_point_id(chunk_id)

            # Per-chunk DB row (Section 11.4.5: body_text is source of truth)
            row = RagDocument(
                id=str(uuid.uuid4()),
                source_document_id=chunk_id,  # chunk_id uniquely identifies each chunk row
                scope=scope,
                owner_user_id=owner_user_id,
                title=title,
                source_citation=source_citation,
                categories_json=categories_json,
                embedding_model=_EMBEDDING_MODEL_ID,
                content_hash=content_hash,
                qdrant_collection=self.collection_name,
                qdrant_point_id=point_id,
                chunk_index=chunk_index,
                body_text=chunk_text,
                verified=1 if verified else 0,
            )
            db_rows.append(row)

            # Qdrant point: Section 11.4.5 — MUST NOT store raw chunk text in payload
            qdrant_points.append(
                {
                    "point_id": point_id,
                    "vector": embedding.tolist(),
                    "payload": {
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                        "chunk_index": chunk_index,
                        "title": title,
                        "verified": 1 if verified else 0,
                    },
                }
            )

        # Persist DB rows then upsert to Qdrant
        self.db.add_all(db_rows)
        self.db.commit()
        self._qdrant.upsert_documents(qdrant_points)

        logger.info(
            "RAGService.ingest: document_id={} title={!r} chunks={} content_hash={}...",
            document_id,
            title,
            len(chunks),
            content_hash[:16],
        )
        return {
            "document_id": document_id,
            "chunk_count": len(chunks),
            "content_hash": content_hash,
        }

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
        verified_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant chunks for *query* (Section 11.4.5).

        Embeds the query, performs ANN search in Qdrant, applies score
        filtering, derives chunk text from the DB (not Qdrant payload), and
        returns results in the deterministic tie-break order required by
        Section 11.4.5.

        Deterministic ordering (Section 11.4.5):
        1. ``score DESC``
        2. ``verified DESC``
        3. ``rag_document_id ASC``
        4. ``chunk_index ASC``

        Args:
            query: Natural-language query string.
            top_k: Maximum results to return (default: 5).
            min_score: Minimum cosine similarity threshold (default: 0.70).
            verified_only: Restrict results to verified documents.

        Returns:
            List of citation dicts, each containing:
            ``rag_document_id``, ``chunk_id``, ``chunk_index``,
            ``relevance_score``, ``snippet``, ``verified``, ``title``.
            Empty list on error or no qualifying matches.
        """
        if self._embedder is None:
            logger.warning("RAGService.retrieve: embedding model unavailable; returning []")
            return []

        effective_top_k = top_k if top_k is not None else self.top_k
        effective_min_score = min_score if min_score is not None else self.min_score

        # Embed the query
        try:
            query_vector: list[float] = self._embedder.encode(query).tolist()
        except Exception as exc:
            logger.warning("RAGService.retrieve: failed to encode query: {}", exc)
            return []

        # Fetch from Qdrant with a wider limit to allow post-filtering
        fetch_limit = effective_top_k * 3 if verified_only else effective_top_k * 2
        raw_hits = self._qdrant.search(query_vector, limit=fetch_limit)

        # Filter: score threshold + verified_only
        filtered = [
            h
            for h in raw_hits
            if h["score"] >= effective_min_score
            and (
                not verified_only
                or (h.get("payload") or {}).get("verified", 0) == 1
            )
        ]

        # Deterministic tie-break ordering (Section 11.4.5)
        filtered.sort(
            key=lambda h: (
                -h["score"],
                -((h.get("payload") or {}).get("verified", 0)),
                (h.get("payload") or {}).get("document_id", ""),
                (h.get("payload") or {}).get("chunk_index", 0),
            )
        )
        filtered = filtered[:effective_top_k]

        if not filtered:
            return []

        # Resolve chunk texts from DB (Section 11.4.5: canonical source of truth)
        chunk_ids = [
            (h.get("payload") or {}).get("chunk_id", "") for h in filtered
        ]
        rows_by_chunk_id: dict[str, RagDocument] = {}
        for row in (
            self.db.query(RagDocument)
            .filter(RagDocument.source_document_id.in_(chunk_ids))
            .all()
        ):
            rows_by_chunk_id[row.source_document_id] = row

        citations: list[dict[str, Any]] = []
        for hit in filtered:
            payload = hit.get("payload") or {}
            chunk_id: str = payload.get("chunk_id", "")
            document_id: str = payload.get("document_id", "")
            chunk_index: int = payload.get("chunk_index", 0)

            row = rows_by_chunk_id.get(chunk_id)
            if row is None:
                logger.warning(
                    "RAGService.retrieve: no DB row for chunk_id={}, skipping",
                    chunk_id,
                )
                continue

            citations.append(
                {
                    "rag_document_id": document_id,
                    "chunk_id": chunk_id,
                    "chunk_index": chunk_index,
                    "relevance_score": hit["score"],
                    "snippet": row.body_text[:200],
                    "verified": bool(row.verified),
                    "title": row.title,
                }
            )

        logger.debug(
            "RAGService.retrieve: query={!r} raw_hits={} citations={}",
            query[:60],
            len(raw_hits),
            len(citations),
        )
        return citations

    def get_chunk_text(self, chunk_id: str) -> str | None:
        """Derive chunk text from DB for a given chunk_id (Section 11.4.5).

        Args:
            chunk_id: Chunk ID in format ``'{doc_id}#chunk:{N}'``.

        Returns:
            ``body_text`` of the matching :class:`RagDocument`, or ``None``
            if no row exists for *chunk_id*.
        """
        row = (
            self.db.query(RagDocument)
            .filter(RagDocument.source_document_id == chunk_id)
            .first()
        )
        return row.body_text if row else None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_chunker_config_hash(self) -> str:
        """Compute SHA-256 hash of the canonical chunker config (Section 11.4.3.2).

        Executors MUST log ``chunker_algorithm_id``, ``chunker_version``, and
        ``chunker_config_hash``.
        """
        from src.ai.contracts import canonical_serialize_jcs, normalize_for_hashing

        config = normalize_for_hashing(
            {
                "chunker_algorithm_id": _CHUNKER_ALGORITHM_ID,
                "chunker_version": _CHUNKER_VERSION,
                "tokenizer_id": _TOKENIZER_ID,
                "tokenizer_version": _TOKENIZER_VERSION,
                "chunk_size_tokens": self.chunk_size_tokens,
                "chunk_overlap_tokens": self.chunk_overlap_tokens,
                "separator_policy": "whitespace",
            }
        )
        return hashlib.sha256(canonical_serialize_jcs(config)).hexdigest()


# ---------------------------------------------------------------------------
# Module-level pure functions (deterministic, no side effects)
# ---------------------------------------------------------------------------


def _normalize_text(raw_text: str) -> str:
    """Text normalization algorithm (Section 11.4.3.1).

    Steps applied in order:

    1. Unicode NFC normalize the entire string.
    2. Normalize line endings: ``\\r\\n`` and ``\\r`` → ``\\n``.
    3. Normalize whitespace classes (Unicode ``Zs``, ``\\t``, ``\\u00A0``) to
       ASCII space ``0x20``.
    4. Preserve paragraph breaks: any run of 2+ ``\\n`` → exactly ``\\n\\n``.
    5. Single-line spacing: within each paragraph collapse runs of 2+ spaces
       to a single space.
    6. Trim leading/trailing spaces on each paragraph; trim full text.

    Args:
        raw_text: Original document text.

    Returns:
        Normalized text string (``normalized_text`` in spec).
    """
    # 1. Unicode NFC
    text = unicodedata.normalize("NFC", raw_text)

    # 2. Line-ending normalization
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Normalize whitespace-class characters to ASCII space
    def _to_space(char: str) -> str:
        if char in ("\t", "\u00A0"):
            return " "
        if unicodedata.category(char) == "Zs":
            return " "
        return char

    text = "".join(_to_space(c) for c in text)

    # 4. Paragraph-break normalization: 2+ newlines → exactly "\n\n"
    text = re.sub(r"\n{2,}", "\n\n", text)

    # 5 + 6. Per-paragraph: collapse spaces, trim edges
    paragraphs = text.split("\n\n")
    normalized_paragraphs: list[str] = []
    for para in paragraphs:
        para = re.sub(r" {2,}", " ", para)  # collapse 2+ spaces
        para = para.strip(" ")  # trim leading/trailing spaces
        normalized_paragraphs.append(para)

    # Rejoin and strip full text
    return "\n\n".join(normalized_paragraphs).strip()


def _chunk_text(
    normalized_text: str,
    chunk_size_tokens: int = _DEFAULT_CHUNK_SIZE_TOKENS,
    chunk_overlap_tokens: int = _DEFAULT_CHUNK_OVERLAP_TOKENS,
) -> list[dict[str, Any]]:
    """Deterministic whitespace-based chunking (Section 11.4.3.2).

    Tokenization uses simple whitespace splitting (a fixed, deterministic
    approximation of subword tokenization).  The same input always produces
    the same chunks.

    Args:
        normalized_text: Pre-normalized text from :func:`_normalize_text`.
        chunk_size_tokens: Maximum token count per chunk (default 512).
        chunk_overlap_tokens: Number of overlapping tokens between adjacent
            chunks (default 50).

    Returns:
        List of ``{"chunk_index": int, "text": str}`` dicts.

    Raises:
        ValueError: If ``chunk_overlap_tokens >= chunk_size_tokens``.
    """
    if chunk_overlap_tokens >= chunk_size_tokens:
        raise ValueError(
            f"chunk_overlap_tokens ({chunk_overlap_tokens}) must be < "
            f"chunk_size_tokens ({chunk_size_tokens})"
        )

    tokens = normalized_text.split()
    if not tokens:
        return []

    step = chunk_size_tokens - chunk_overlap_tokens
    chunks: list[dict[str, Any]] = []
    chunk_index = 0
    i = 0
    while i < len(tokens):
        window = tokens[i : i + chunk_size_tokens]
        chunks.append({"chunk_index": chunk_index, "text": " ".join(window)})
        i += step
        chunk_index += 1

    return chunks


def _make_chunk_id(document_id: str, chunk_index: int) -> str:
    """Format a canonical chunk_id (Section 11.4.4).

    Format: ``"{rag_document_id}#chunk:{chunk_index}"`` with decimal
    ``chunk_index`` and **no zero-padding**.

    Args:
        document_id: 32-hex logical document identifier.
        chunk_index: Zero-based chunk index (no padding).

    Returns:
        Chunk ID string, e.g. ``"abcd1234...#chunk:3"``.
    """
    return f"{document_id}#chunk:{chunk_index}"


def _make_point_id(chunk_id: str) -> str:
    """Compute deterministic Qdrant point ID (Section 11.4.4).

    ``point_id = UUIDv5(RAG_GLOBAL_KB_NAMESPACE_UUID, chunk_id)``

    The namespace constant :data:`RAG_GLOBAL_KB_NAMESPACE_UUID` MUST be the
    hardcoded UUID ``"2a9e7c2c-6b79-4d33-9f2d-2b3e3e5c65b4"``; it MUST NOT
    be derived from a text literal.

    Args:
        chunk_id: Canonical chunk ID string.

    Returns:
        UUID string (with dashes), e.g.
        ``"b3a0c467-d544-5ba9-a8df-ea946ffd32eb"``.
    """
    return str(uuid.uuid5(RAG_GLOBAL_KB_NAMESPACE_UUID, chunk_id))
