"""Load local markdown docs into rag_documents table and Qdrant with validations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from src.ai.ollama import OllamaClient
from src.ai.qdrant import QdrantClientAdapter
from src.db.models.rag import RagDocument
from src.db.session import db_session


def _stable_point_id(content_hash: str, idx: int) -> str:
    return f"doc-{idx}-{content_hash[:16]}"


def load_docs(
    source_dir: Path,
    collection: str,
    *,
    expected_min_docs: int = 1,
    dry_run: bool = False,
) -> dict[str, Any]:
    ollama = OllamaClient()
    qdrant = QdrantClientAdapter(collection=collection)
    qdrant.ensure_collection()

    files = sorted([p for p in source_dir.rglob("*.md") if p.is_file()])
    if len(files) < expected_min_docs:
        raise ValueError(
            f"insufficient markdown documents: found {len(files)}, expected >= {expected_min_docs}"
        )

    inserted = 0
    skipped_existing = 0
    embedding_dims: set[int] = set()

    with db_session() as db:
        for idx, path in enumerate(files):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if not text.strip():
                continue
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

            existing = (
                db.query(RagDocument)
                .filter(
                    RagDocument.scope == "global",
                    RagDocument.content_hash == digest,
                    RagDocument.qdrant_collection == collection,
                )
                .one_or_none()
            )
            if existing is not None:
                skipped_existing += 1
                continue

            vector = ollama.embed(text[:4000])
            embedding_dims.add(len(vector))
            if len(vector) != qdrant.vector_size:
                raise ValueError(
                    f"embedding dimension mismatch for {path}: got {len(vector)}, expected {qdrant.vector_size}"
                )

            point_id = _stable_point_id(digest, idx)

            if not dry_run:
                doc = RagDocument(
                    scope="global",
                    owner_user_id=None,
                    title=path.name,
                    source_citation=str(path),
                    content_hash=digest,
                    qdrant_collection=collection,
                    qdrant_point_id=point_id,
                    chunk_index=0,
                    body_text=text,
                    verified=1,
                )
                db.add(doc)
                qdrant.upsert_documents(
                    [
                        {
                            "point_id": point_id,
                            "vector": vector,
                            "payload": {
                                "title": path.name,
                                "source": str(path),
                                "hash": digest,
                            },
                        }
                    ]
                )

            inserted += 1

    probe_hits = qdrant.search([0.0] * qdrant.vector_size, limit=3)
    return {
        "source": str(source_dir),
        "collection": collection,
        "files_seen": len(files),
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "embedding_dimensions": sorted(embedding_dims),
        "qdrant_probe_count": len(probe_hits),
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", default="docs", help="Directory containing markdown docs"
    )
    parser.add_argument("--collection", default="rag_documents")
    parser.add_argument(
        "--expected-min-docs",
        type=int,
        default=1,
        help="Fail if fewer markdown docs than this are discovered.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = load_docs(
        Path(args.source),
        args.collection,
        expected_min_docs=args.expected_min_docs,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
