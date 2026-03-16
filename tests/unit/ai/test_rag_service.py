"""Unit tests for src/ai/rag/rag_service.py.

Tests cover:
- Text normalization algorithm (Section 11.4.3.1)
- Deterministic chunking (Section 11.4.3.2)
- chunk_id format (Section 11.4.4)
- point_id UUIDv5 test vectors (Section 11.4.4)
- RAGService ingestion and retrieval (mocked Qdrant + DB)
- Retrieval ordering (Section 11.4.5)
- Minimum similarity threshold enforcement
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.ai.rag.rag_service import (
    RAG_GLOBAL_KB_NAMESPACE_UUID,
    _chunk_text,
    _make_chunk_id,
    _make_point_id,
    _normalize_text,
)


# ---------------------------------------------------------------------------
# Section 11.4.4 namespace constant
# ---------------------------------------------------------------------------


class TestNamespaceConstant:
    def test_namespace_is_correct_uuid(self):
        assert str(RAG_GLOBAL_KB_NAMESPACE_UUID) == "2a9e7c2c-6b79-4d33-9f2d-2b3e3e5c65b4"

    def test_namespace_is_uuid_object(self):
        assert isinstance(RAG_GLOBAL_KB_NAMESPACE_UUID, uuid.UUID)


# ---------------------------------------------------------------------------
# Section 11.4.4 — chunk_id format
# ---------------------------------------------------------------------------


class TestMakeChunkId:
    def test_basic_format(self):
        doc_id = "a" * 32
        assert _make_chunk_id(doc_id, 0) == f"{'a'*32}#chunk:0"

    def test_no_zero_padding(self):
        doc_id = "b" * 32
        cid = _make_chunk_id(doc_id, 7)
        assert cid == f"{'b'*32}#chunk:7"
        assert "#chunk:07" not in cid

    def test_large_chunk_index(self):
        doc_id = "c" * 32
        assert _make_chunk_id(doc_id, 12) == f"{'c'*32}#chunk:12"

    def test_chunk_id_prefixed_with_doc_id(self):
        doc_id = "0123456789abcdef0123456789abcdef"
        cid = _make_chunk_id(doc_id, 3)
        assert cid.startswith(doc_id)


# ---------------------------------------------------------------------------
# Section 11.4.4 — UUIDv5 point ID test vectors (MUST pass)
# ---------------------------------------------------------------------------


class TestMakePointId:
    def test_vector_aaa_chunk_0(self):
        """Test vector from architecture: aaaaa...a + chunk:0."""
        doc_id = "a" * 32
        chunk_id = _make_chunk_id(doc_id, 0)
        point_id = _make_point_id(chunk_id)
        assert point_id == "b3a0c467-d544-5ba9-a8df-ea946ffd32eb"

    def test_vector_aaa_chunk_7(self):
        """Test vector from architecture: aaaaa...a + chunk:7."""
        doc_id = "a" * 32
        chunk_id = _make_chunk_id(doc_id, 7)
        point_id = _make_point_id(chunk_id)
        assert point_id == "9a140d87-7260-5466-b5f2-b45627061c16"

    def test_vector_0123_chunk_12(self):
        """Test vector from architecture: 0123456789abcdef... + chunk:12."""
        doc_id = "0123456789abcdef0123456789abcdef"
        chunk_id = _make_chunk_id(doc_id, 12)
        point_id = _make_point_id(chunk_id)
        assert point_id == "fb8c5abd-12c5-557b-a3cb-4b8c08bae37e"

    def test_deterministic_same_input(self):
        chunk_id = "deadbeef" * 4 + "#chunk:5"
        assert _make_point_id(chunk_id) == _make_point_id(chunk_id)

    def test_different_chunks_different_point_ids(self):
        doc_id = "f" * 32
        pid0 = _make_point_id(_make_chunk_id(doc_id, 0))
        pid1 = _make_point_id(_make_chunk_id(doc_id, 1))
        assert pid0 != pid1

    def test_returns_valid_uuid_string(self):
        chunk_id = _make_chunk_id("e" * 32, 0)
        pid = _make_point_id(chunk_id)
        uuid.UUID(pid)  # raises if not a valid UUID string


# ---------------------------------------------------------------------------
# Section 11.4.3.1 — Text normalization
# ---------------------------------------------------------------------------


class TestNormalizeText:
    def test_nfc_normalization(self):
        # "é" as NFD (e + combining acute) → NFC
        nfd_e = "e\u0301"
        result = _normalize_text(nfd_e)
        assert result == "\u00e9"

    def test_crlf_to_lf(self):
        text = "line1\r\nline2\r\nline3"
        result = _normalize_text(text)
        assert "\r" not in result
        assert result == "line1\nline2\nline3"

    def test_cr_to_lf(self):
        result = _normalize_text("a\rb")
        assert result == "a\nb"

    def test_tab_to_space(self):
        result = _normalize_text("hello\tworld")
        assert result == "hello world"

    def test_nbsp_to_space(self):
        result = _normalize_text("hello\u00A0world")
        assert result == "hello world"

    def test_unicode_zs_to_space(self):
        # \u2002 (en space) is category Zs
        result = _normalize_text("a\u2002b")
        assert result == "a b"

    def test_paragraph_break_normalization(self):
        # 3 newlines → exactly \n\n
        result = _normalize_text("para1\n\n\n\npara2")
        assert result == "para1\n\npara2"

    def test_double_newline_preserved(self):
        result = _normalize_text("para1\n\npara2")
        assert result == "para1\n\npara2"

    def test_multiple_spaces_collapsed(self):
        result = _normalize_text("hello   world")
        assert result == "hello world"

    def test_leading_trailing_whitespace_trimmed(self):
        result = _normalize_text("  hello world  ")
        assert result == "hello world"

    def test_empty_string(self):
        assert _normalize_text("") == ""

    def test_deterministic(self):
        text = "Hello  World\r\n\r\nFoo\tBar"
        assert _normalize_text(text) == _normalize_text(text)

    def test_complex_document(self):
        raw = "  Title\r\n\r\n\r\nParagraph  one.\n\nParagraph\ttwo.  "
        result = _normalize_text(raw)
        assert "\r" not in result
        assert "\t" not in result
        assert "  " not in result  # no double spaces
        assert result.startswith("Title")
        assert result.endswith("Paragraph two.")


# ---------------------------------------------------------------------------
# Section 11.4.3.2 — Chunking
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_single_chunk_short_text(self):
        text = "hello world"
        chunks = _chunk_text(text, chunk_size_tokens=512, chunk_overlap_tokens=50)
        assert len(chunks) == 1
        assert chunks[0]["chunk_index"] == 0
        assert chunks[0]["text"] == "hello world"

    def test_exact_chunk_size(self):
        tokens = ["word"] * 512
        text = " ".join(tokens)
        chunks = _chunk_text(text, chunk_size_tokens=512, chunk_overlap_tokens=50)
        assert chunks[0]["chunk_index"] == 0
        assert len(chunks[0]["text"].split()) == 512

    def test_overlap_creates_multiple_chunks(self):
        # 600 tokens with size=512, overlap=50 → step=462 → 2 chunks
        tokens = [f"w{i}" for i in range(600)]
        text = " ".join(tokens)
        chunks = _chunk_text(text, chunk_size_tokens=512, chunk_overlap_tokens=50)
        assert len(chunks) == 2
        assert chunks[0]["chunk_index"] == 0
        assert chunks[1]["chunk_index"] == 1

    def test_chunk_indices_sequential(self):
        tokens = [f"tok{i}" for i in range(2000)]
        text = " ".join(tokens)
        chunks = _chunk_text(text, chunk_size_tokens=512, chunk_overlap_tokens=50)
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_index"] == i

    def test_deterministic_same_output(self):
        text = " ".join([f"w{i}" for i in range(1000)])
        c1 = _chunk_text(text)
        c2 = _chunk_text(text)
        assert c1 == c2

    def test_empty_text_returns_empty(self):
        assert _chunk_text("") == []

    def test_overlap_constraint(self):
        with pytest.raises(ValueError, match="chunk_overlap_tokens"):
            _chunk_text("hello world", chunk_size_tokens=10, chunk_overlap_tokens=10)

    def test_overlap_greater_raises(self):
        with pytest.raises(ValueError):
            _chunk_text("hello world", chunk_size_tokens=10, chunk_overlap_tokens=15)

    def test_chunks_have_overlap_tokens(self):
        """Adjacent chunks share overlap_tokens words."""
        tokens = [f"w{i}" for i in range(100)]
        text = " ".join(tokens)
        chunks = _chunk_text(text, chunk_size_tokens=20, chunk_overlap_tokens=5)
        if len(chunks) >= 2:
            c0_words = chunks[0]["text"].split()
            c1_words = chunks[1]["text"].split()
            # Last 5 words of chunk 0 should be first 5 of chunk 1
            assert c0_words[-5:] == c1_words[:5]

    def test_no_chunk_id_padding(self):
        """chunk_index values are decimal, no zero-padding."""
        tokens = [f"w{i}" for i in range(3000)]
        text = " ".join(tokens)
        chunks = _chunk_text(text, chunk_size_tokens=512, chunk_overlap_tokens=50)
        for chunk in chunks:
            # chunk_index should be plain int
            assert isinstance(chunk["chunk_index"], int)
            # When used in chunk_id, must not have padding
            cid = _make_chunk_id("a" * 32, chunk["chunk_index"])
            assert "#chunk:0" not in cid or chunk["chunk_index"] == 0


# ---------------------------------------------------------------------------
# Section 11.4.5 — Retrieval (RAGService, mocked)
# ---------------------------------------------------------------------------


def _make_mock_service(db=None, hits=None):
    """Build a RAGService with mocked Qdrant and sentence-transformers."""
    db = db or MagicMock()
    with (
        patch("src.ai.rag.rag_service.QdrantClientAdapter") as mock_qdrant_cls,
        patch("src.ai.rag.rag_service._load_sentence_transformer_lib") as mock_st,
    ):
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = hits or []
        mock_qdrant_cls.return_value = mock_qdrant

        mock_embedder = MagicMock()
        mock_embedder.encode.return_value = MagicMock(tolist=lambda: [0.1] * 768)
        mock_st_lib = MagicMock(return_value=mock_embedder)
        mock_st.return_value = mock_st_lib

        from src.ai.rag.rag_service import RAGService

        svc = RAGService(db=db)
        svc._qdrant = mock_qdrant
        svc._embedder = mock_embedder
        return svc, mock_qdrant, mock_embedder, db


class TestRAGServiceRetrieve:
    def _make_hit(self, chunk_id: str, document_id: str, chunk_index: int, score: float, verified: int = 0):
        return {
            "point_id": str(uuid.uuid4()),
            "score": score,
            "payload": {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "chunk_index": chunk_index,
                "verified": verified,
                "title": "Test Doc",
            },
        }

    def test_returns_empty_when_no_hits(self):
        svc, qdrant, _, db = _make_mock_service(hits=[])
        db.query.return_value.filter.return_value.all.return_value = []
        result = svc.retrieve("test query")
        assert result == []

    def test_min_score_threshold_enforced(self):
        doc_id = "a" * 32
        cid = _make_chunk_id(doc_id, 0)
        low_hit = self._make_hit(cid, doc_id, 0, score=0.5)  # below threshold
        svc, qdrant, _, db = _make_mock_service(hits=[low_hit])
        db.query.return_value.filter.return_value.all.return_value = []
        result = svc.retrieve("test query", min_score=0.7)
        assert result == []

    def test_above_threshold_returned(self):
        doc_id = "b" * 32
        cid = _make_chunk_id(doc_id, 0)
        hit = self._make_hit(cid, doc_id, 0, score=0.85)
        svc, qdrant, _, db = _make_mock_service(hits=[hit])

        mock_row = MagicMock()
        mock_row.source_document_id = cid
        mock_row.body_text = "chunk content here"
        mock_row.verified = 0
        mock_row.title = "Test Doc"
        db.query.return_value.filter.return_value.all.return_value = [mock_row]

        result = svc.retrieve("test query", min_score=0.7)
        assert len(result) == 1
        assert result[0]["rag_document_id"] == doc_id
        assert result[0]["chunk_id"] == cid
        assert result[0]["relevance_score"] == 0.85
        assert result[0]["snippet"] == "chunk content here"

    def test_snippet_truncated_to_200_chars(self):
        doc_id = "c" * 32
        cid = _make_chunk_id(doc_id, 0)
        hit = self._make_hit(cid, doc_id, 0, score=0.9)
        svc, _, _, db = _make_mock_service(hits=[hit])

        long_text = "x" * 500
        mock_row = MagicMock()
        mock_row.source_document_id = cid
        mock_row.body_text = long_text
        mock_row.verified = 0
        mock_row.title = "T"
        db.query.return_value.filter.return_value.all.return_value = [mock_row]

        result = svc.retrieve("q")
        assert len(result[0]["snippet"]) == 200

    def test_deterministic_ordering_score_desc(self):
        """Higher score should come first."""
        doc_id = "d" * 32
        cid0 = _make_chunk_id(doc_id, 0)
        cid1 = _make_chunk_id(doc_id, 1)
        hits = [
            self._make_hit(cid1, doc_id, 1, score=0.75),
            self._make_hit(cid0, doc_id, 0, score=0.90),
        ]
        svc, _, _, db = _make_mock_service(hits=hits)

        rows = []
        for cid, idx in [(cid0, 0), (cid1, 1)]:
            r = MagicMock()
            r.source_document_id = cid
            r.body_text = f"chunk {idx}"
            r.verified = 0
            r.title = "T"
            rows.append(r)
        db.query.return_value.filter.return_value.all.return_value = rows

        result = svc.retrieve("q")
        assert result[0]["chunk_index"] == 0  # score=0.90 first
        assert result[1]["chunk_index"] == 1  # score=0.75 second

    def test_verified_only_filters_unverified(self):
        doc_id = "e" * 32
        cid_v = _make_chunk_id(doc_id, 0)
        cid_u = _make_chunk_id(doc_id, 1)
        hits = [
            self._make_hit(cid_v, doc_id, 0, score=0.8, verified=1),
            self._make_hit(cid_u, doc_id, 1, score=0.9, verified=0),  # unverified
        ]
        svc, _, _, db = _make_mock_service(hits=hits)

        r = MagicMock()
        r.source_document_id = cid_v
        r.body_text = "verified content"
        r.verified = 1
        r.title = "T"
        db.query.return_value.filter.return_value.all.return_value = [r]

        result = svc.retrieve("q", verified_only=True)
        assert len(result) == 1
        assert result[0]["verified"] is True

    def test_top_k_respected(self):
        doc_id = "f" * 32
        hits = [
            self._make_hit(_make_chunk_id(doc_id, i), doc_id, i, score=0.9 - i * 0.01)
            for i in range(10)
        ]
        svc, _, _, db = _make_mock_service(hits=hits)

        rows = []
        for i in range(10):
            cid = _make_chunk_id(doc_id, i)
            r = MagicMock()
            r.source_document_id = cid
            r.body_text = f"chunk {i}"
            r.verified = 0
            r.title = "T"
            rows.append(r)
        db.query.return_value.filter.return_value.all.return_value = rows

        result = svc.retrieve("q", top_k=3)
        assert len(result) == 3

    def test_no_chunk_text_in_qdrant_payload(self):
        """Verify we do NOT read body_text from Qdrant payload (Section 11.4.5)."""
        doc_id = "a" * 32
        cid = _make_chunk_id(doc_id, 0)
        # Qdrant payload intentionally has NO body_text key
        hit = {
            "point_id": str(uuid.uuid4()),
            "score": 0.85,
            "payload": {
                "chunk_id": cid,
                "document_id": doc_id,
                "chunk_index": 0,
                "verified": 0,
                "title": "T",
                # No "body_text" key — architecture 11.4.5 compliance
            },
        }
        svc, _, _, db = _make_mock_service(hits=[hit])

        mock_row = MagicMock()
        mock_row.source_document_id = cid
        mock_row.body_text = "from DB only"
        mock_row.verified = 0
        mock_row.title = "T"
        db.query.return_value.filter.return_value.all.return_value = [mock_row]

        result = svc.retrieve("q")
        assert result[0]["snippet"] == "from DB only"

    def test_returns_empty_when_embedder_unavailable(self):
        svc, _, _, _ = _make_mock_service()
        svc._embedder = None
        result = svc.retrieve("test")
        assert result == []


# ---------------------------------------------------------------------------
# Section 11.4.5 — get_chunk_text
# ---------------------------------------------------------------------------


class TestGetChunkText:
    def test_returns_body_text_when_found(self):
        svc, _, _, db = _make_mock_service()
        mock_row = MagicMock()
        mock_row.body_text = "the chunk text"
        db.query.return_value.filter.return_value.first.return_value = mock_row
        assert svc.get_chunk_text("abc#chunk:0") == "the chunk text"

    def test_returns_none_when_not_found(self):
        svc, _, _, db = _make_mock_service()
        db.query.return_value.filter.return_value.first.return_value = None
        assert svc.get_chunk_text("nonexistent#chunk:99") is None


# ---------------------------------------------------------------------------
# Content hash (Section 11.4 + 11.0.4)
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_sha256_of_normalized_text(self):
        text = "Hello World"
        normalized = _normalize_text(text)
        expected_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        assert len(expected_hash) == 64
        assert expected_hash == hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def test_content_hash_deterministic(self):
        text = "Same input\r\nevery time."
        h1 = hashlib.sha256(_normalize_text(text).encode("utf-8")).hexdigest()
        h2 = hashlib.sha256(_normalize_text(text).encode("utf-8")).hexdigest()
        assert h1 == h2

    def test_different_text_different_hash(self):
        h1 = hashlib.sha256(_normalize_text("text A").encode("utf-8")).hexdigest()
        h2 = hashlib.sha256(_normalize_text("text B").encode("utf-8")).hexdigest()
        assert h1 != h2


# ---------------------------------------------------------------------------
# RAGService.ingest_document (mocked)
# ---------------------------------------------------------------------------


class TestRAGServiceIngest:
    def _make_ingest_service(self):
        db = MagicMock()
        db.add_all = MagicMock()
        db.commit = MagicMock()

        with (
            patch("src.ai.rag.rag_service.QdrantClientAdapter") as mock_qdrant_cls,
            patch("src.ai.rag.rag_service._load_sentence_transformer_lib") as mock_st,
        ):
            mock_qdrant = MagicMock()
            mock_qdrant_cls.return_value = mock_qdrant

            import numpy as np

            mock_embedder = MagicMock()
            # Return a batch of embeddings matching chunk count
            mock_embedder.encode.side_effect = lambda texts, **kw: np.zeros(
                (len(texts), 768), dtype="float32"
            )
            mock_st_lib = MagicMock(return_value=mock_embedder)
            mock_st.return_value = mock_st_lib

            from src.ai.rag.rag_service import RAGService

            svc = RAGService(db=db)
            svc._qdrant = mock_qdrant
            svc._embedder = mock_embedder
            return svc, mock_qdrant, db

    def test_returns_document_id_and_chunk_count(self):
        svc, _, _ = self._make_ingest_service()
        result = svc.ingest_document("Test", "word " * 100)
        assert "document_id" in result
        assert "chunk_count" in result
        assert "content_hash" in result
        assert len(result["document_id"]) == 32  # 32-hex
        assert result["chunk_count"] >= 1

    def test_document_id_is_32_hex(self):
        svc, _, _ = self._make_ingest_service()
        result = svc.ingest_document("T", "some content here")
        assert len(result["document_id"]) == 32
        assert result["document_id"] == result["document_id"].lower()
        int(result["document_id"], 16)  # valid hex

    def test_content_hash_is_64_hex(self):
        svc, _, _ = self._make_ingest_service()
        result = svc.ingest_document("T", "some content here")
        assert len(result["content_hash"]) == 64

    def test_qdrant_upsert_called(self):
        svc, mock_qdrant, _ = self._make_ingest_service()
        svc.ingest_document("Test", "word " * 20)
        assert mock_qdrant.upsert_documents.called

    def test_qdrant_payload_has_no_body_text(self):
        """Section 11.4.5: Qdrant payload MUST NOT contain raw chunk text."""
        svc, mock_qdrant, _ = self._make_ingest_service()
        svc.ingest_document("Test", "word " * 20)

        call_args = mock_qdrant.upsert_documents.call_args[0][0]
        for point in call_args:
            assert "body_text" not in point["payload"]
            assert "text" not in point["payload"]

    def test_qdrant_payload_has_chunk_id_and_document_id(self):
        svc, mock_qdrant, _ = self._make_ingest_service()
        svc.ingest_document("Test", "word " * 20)

        call_args = mock_qdrant.upsert_documents.call_args[0][0]
        for point in call_args:
            assert "chunk_id" in point["payload"]
            assert "document_id" in point["payload"]
            assert "chunk_index" in point["payload"]

    def test_chunk_ids_follow_format(self):
        svc, mock_qdrant, _ = self._make_ingest_service()
        result = svc.ingest_document("Test", "word " * 20)
        doc_id = result["document_id"]

        call_args = mock_qdrant.upsert_documents.call_args[0][0]
        for i, point in enumerate(call_args):
            chunk_id = point["payload"]["chunk_id"]
            assert chunk_id == f"{doc_id}#chunk:{i}"

    def test_db_commit_called(self):
        svc, _, db = self._make_ingest_service()
        svc.ingest_document("T", "hello world")
        assert db.commit.called

    def test_raises_if_embedder_unavailable(self):
        svc, _, _ = self._make_ingest_service()
        svc._embedder = None
        with pytest.raises(RuntimeError, match="Embedding model unavailable"):
            svc.ingest_document("T", "content")
