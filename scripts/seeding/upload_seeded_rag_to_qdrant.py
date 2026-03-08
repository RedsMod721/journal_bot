"""Seed Window B uploader: embed seeded rag_documents rows into Qdrant."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.ai.ollama import OllamaClient
from src.ai.qdrant import QdrantClientAdapter
from src.db.models.rag import RagDocument
from src.db.session import db_session


def _point_id(doc: RagDocument) -> str:
    return str(doc.qdrant_point_id or doc.source_document_id or doc.id)


def _embed_text(doc: RagDocument) -> str:
    title = (doc.title or "").strip()
    body = (doc.body_text or "").strip()
    text = f"{title}\n\n{body}".strip()
    return text[:4000]


def upload_seeded_rag(
    *,
    expected_min_docs: int = 1000,
    batch_size: int = 32,
    max_docs: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    ollama = OllamaClient()
    qdrant = QdrantClientAdapter()
    qdrant.ensure_collection()

    with db_session() as db:
        query = (
            db.query(RagDocument)
            .filter(RagDocument.scope == "global")
            .order_by(RagDocument.id.asc())
        )
        if max_docs is not None:
            query = query.limit(max_docs)
        docs = query.all()

    if len(docs) < expected_min_docs:
        raise ValueError(
            f"insufficient seeded rag docs: found {len(docs)}, expected >= {expected_min_docs}"
        )

    embedded = 0
    upserted = 0
    skipped_empty = 0
    embedding_dims: set[int] = set()
    probe_vector: list[float] | None = None
    batch: list[dict[str, Any]] = []

    for doc in docs:
        text = _embed_text(doc)
        if not text:
            skipped_empty += 1
            continue

        vector = ollama.embed(text)
        embedding_dims.add(len(vector))
        if len(vector) != qdrant.vector_size:
            raise ValueError(
                f"embedding dimension mismatch for point_id={_point_id(doc)}: "
                f"got {len(vector)}, expected {qdrant.vector_size}"
            )

        if probe_vector is None:
            probe_vector = vector

        batch.append(
            {
                "point_id": _point_id(doc),
                "vector": vector,
                "payload": {
                    "title": doc.title,
                    "source": doc.source_citation,
                    "publication_date": doc.publication_date,
                    "doi_link": doc.doi_link,
                    "scope": doc.scope,
                },
            }
        )
        embedded += 1

        if len(batch) >= batch_size:
            if not dry_run:
                qdrant.upsert_documents(batch)
            upserted += len(batch)
            batch = []

    if batch:
        if not dry_run:
            qdrant.upsert_documents(batch)
        upserted += len(batch)

    if dry_run or probe_vector is None:
        probe_hits = []
    else:
        probe_hits = qdrant.search(probe_vector, limit=5)

    return {
        "ok": True,
        "dry_run": dry_run,
        "qdrant_mode": qdrant.mode,
        "qdrant_collection": qdrant.collection,
        "qdrant_vector_size": qdrant.vector_size,
        "ollama_model": ollama.model,
        "rows_seen": len(docs),
        "embedded": embedded,
        "upserted": upserted,
        "skipped_empty": skipped_empty,
        "embedding_dimensions": sorted(embedding_dims),
        "probe_hit_count": len(probe_hits),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expected-min-docs",
        type=int,
        default=1000,
        help="Fail if fewer seeded global docs are found.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Qdrant upsert batch size.",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=None,
        help="Optional cap for local smoke runs.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = upload_seeded_rag(
        expected_min_docs=args.expected_min_docs,
        batch_size=args.batch_size,
        max_docs=args.max_docs,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
