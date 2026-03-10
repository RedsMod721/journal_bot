"""
Upload RAG documents to Qdrant vector database.

Reads from: data/seeds/kb/rag_documents_v1.jsonl
Uploads to: Qdrant collection configured in config/dev.yaml

Usage:
    python scripts/seeding/upload_seeded_rag_to_qdrant.py
    python scripts/seeding/upload_seeded_rag_to_qdrant.py --batch-size 50
    python scripts/seeding/upload_seeded_rag_to_qdrant.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from loguru import logger

if TYPE_CHECKING:
    from src.ai.qdrant import QdrantClient

_DEFAULT_JSONL_PATH = _REPO_ROOT / "data" / "seeds" / "kb" / "rag_documents_v1.jsonl"
_DEFAULT_BATCH_SIZE = 100


def _extract_collection_vector_size(collection_info: Any) -> int | None:
    """Return the vector dimension from Qdrant collection metadata."""
    vectors = getattr(getattr(collection_info, "config", None), "params", None)
    vectors = getattr(vectors, "vectors", None)
    if vectors is None:
        return None

    if hasattr(vectors, "size"):
        try:
            return int(vectors.size)
        except Exception:
            return None

    if isinstance(vectors, dict):
        first = next(iter(vectors.values()), None)
        if first is not None and hasattr(first, "size"):
            try:
                return int(first.size)
            except Exception:
                return None

    return None


def _ensure_collection_dimension(client: QdrantClient, expected_dim: int) -> None:
    """Ensure the target collection exists and matches *expected_dim*."""
    if not client.collection_exists():
        logger.info("Collection '{}' not found — creating it now.", client.collection)
        client.create_collection()
        return

    logger.info("Collection '{}' already exists — validating dimension.", client.collection)
    try:
        info = client._adapter.client.get_collection(collection_name=client.collection)
        current_dim = _extract_collection_vector_size(info)
    except Exception as exc:
        logger.warning(
            "Could not inspect collection '{}': {}. Reusing it as-is.",
            client.collection,
            exc,
        )
        return

    if current_dim is None:
        logger.warning(
            "Could not determine vector size for collection '{}'. Reusing it as-is.",
            client.collection,
        )
        return

    if current_dim == expected_dim:
        logger.info(
            "Collection '{}' vector_size={} matches embedding dimension.",
            client.collection,
            current_dim,
        )
        return

    logger.warning(
        "Collection '{}' vector_size={} does not match embedding dimension={}."
        " Recreating collection.",
        client.collection,
        current_dim,
        expected_dim,
    )
    client._adapter.client.delete_collection(collection_name=client.collection)
    client.create_collection()


def _normalize_seed_document(doc: dict[str, Any], line_num: int) -> dict[str, Any]:
    """Normalize seed document schema variants into uploader contract.

    Supported input keys include both legacy and current generator outputs:
    - ``doc_id`` or ``document_id``
    - ``content`` or ``content_markdown``
    - ``category`` or ``categories``

    Args:
        doc: Raw parsed JSON object from a JSONL row.
        line_num: Source line number for precise error messages.

    Returns:
        Normalized document dictionary with canonical keys used by uploader.

    Raises:
        ValueError: If required content is missing after normalization.
    """
    content = doc.get("content") or doc.get("content_markdown")
    if not content:
        raise ValueError(
            "Document on line {} is missing required field 'content' or "
            "'content_markdown': {}".format(line_num, doc)
        )

    doc_id = doc.get("doc_id") or doc.get("document_id")
    categories = doc.get("categories")
    category = doc.get("category")
    tags = doc.get("tags")

    if tags is None:
        if isinstance(categories, list):
            tags = categories
        elif category:
            tags = [category]
        else:
            tags = []

    if category is None and isinstance(categories, list) and categories:
        category = str(categories[0])

    normalized = dict(doc)
    normalized["content"] = content
    normalized["doc_id"] = doc_id
    normalized["category"] = category
    normalized["tags"] = tags
    return normalized


def load_rag_documents(filepath: Path) -> list[dict[str, Any]]:
    """Load RAG documents from a JSONL file.

    Args:
        filepath: Path to rag_documents_v1.jsonl.

    Returns:
        List of document dictionaries.

    Raises:
        FileNotFoundError: If *filepath* does not exist.
        ValueError: If any line is not valid JSON or is missing required content.
    """
    if not filepath.exists():
        raise FileNotFoundError(f"RAG document file not found: {filepath}")

    documents: list[dict[str, Any]] = []
    with filepath.open(encoding="utf-8") as fh:
        for line_num, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_num} of {filepath}: {exc}"
                ) from exc
            documents.append(_normalize_seed_document(doc, line_num))

    return documents


def upload_documents(
    client: QdrantClient,
    documents: list[dict[str, Any]],
    batch_size: int = _DEFAULT_BATCH_SIZE,
    dry_run: bool = False,
) -> int:
    """Upload documents to Qdrant in batches, generating embeddings per document.

    Args:
        client: Initialised :class:`QdrantClient` instance.
        documents: List of RAG document dicts loaded from JSONL.
        batch_size: Number of documents per Qdrant upsert call.
        dry_run: When ``True`` embeddings are generated but nothing is upserted.

    Returns:
        Total number of documents successfully upserted (0 on dry run).

    Raises:
        RuntimeError: If the embedding model is unavailable.
    """
    if client.embedding_model is None:
        raise RuntimeError(
            "Embedding model is not available. "
            "Ensure sentence-transformers is installed and the model can be downloaded."
        )

    expected_dim = len(client._encode_query("dimension probe"))
    _ensure_collection_dimension(client, expected_dim)

    total_docs = len(documents)
    total_batches = (total_docs + batch_size - 1) // batch_size
    upserted = 0

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total_docs)
        batch_docs = documents[start:end]

        logger.info(
            "Uploading batch {}/{} ({} documents, indices {}–{}).",
            batch_idx + 1,
            total_batches,
            len(batch_docs),
            start,
            end - 1,
        )

        points: list[dict[str, Any]] = []
        for doc in batch_docs:
            try:
                vector = client._encode_query(doc["content"])
            except Exception as exc:
                doc_id = doc.get("doc_id", "<unknown>")
                logger.warning(
                    "Failed to encode doc_id='{}': {}. Skipping.", doc_id, exc
                )
                continue

            points.append(
                {
                    "point_id": doc.get("doc_id", str(start + len(points))),
                    "vector": vector,
                    "payload": {
                        "doc_id": doc.get("doc_id"),
                        "content": doc.get("content"),
                        "category": doc.get("category"),
                        "tags": doc.get("tags", []),
                        "source": doc.get("source"),
                        "confidence": doc.get("confidence"),
                    },
                }
            )

        if not dry_run and points:
            try:
                client._adapter.upsert_documents(points)
                upserted += len(points)
            except Exception as exc:
                logger.error(
                    "Batch {}/{} upsert failed: {}. Skipping batch.",
                    batch_idx + 1,
                    total_batches,
                    exc,
                )
        elif dry_run:
            logger.info(
                "Dry run — skipping upsert for batch {}/{}.", batch_idx + 1, total_batches
            )

    return upserted


def verify_upload(client: QdrantClient, expected_count: int) -> bool:
    """Verify the upload by comparing the stored document count to *expected_count*.

    Args:
        client: Initialised :class:`QdrantClient` instance.
        expected_count: Number of documents that were submitted for upload.

    Returns:
        ``True`` if the stored count matches *expected_count*, ``False`` otherwise.
    """
    if expected_count <= 0:
        logger.error(
            "Verification FAILED: uploader reported {} upserts, so success cannot be confirmed.",
            expected_count,
        )
        return False

    actual = client.count_documents()
    if actual >= expected_count:
        logger.info(
            "Verification passed: Qdrant reports {} documents (expected {}).",
            actual,
            expected_count,
        )
        return True

    logger.error(
        "Verification FAILED: Qdrant reports {} documents but expected {}.",
        actual,
        expected_count,
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload seeded RAG documents from JSONL to Qdrant."
    )
    parser.add_argument(
        "--jsonl-path",
        type=Path,
        default=_DEFAULT_JSONL_PATH,
        help="Path to rag_documents_v1.jsonl (default: data/seeds/kb/rag_documents_v1.jsonl).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_DEFAULT_BATCH_SIZE,
        help=f"Documents per Qdrant upsert call (default: {_DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate embeddings but do not write to Qdrant.",
    )
    args = parser.parse_args()

    logger.info("Starting RAG document upload to Qdrant")

    from src.ai.qdrant import QdrantClient

    # ------------------------------------------------------------------
    # 1. Initialise client and verify Qdrant is reachable.
    # ------------------------------------------------------------------
    try:
        client = QdrantClient()
    except Exception as exc:
        logger.error("Failed to initialise QdrantClient: {}", exc)
        return 1

    if not client.is_available():
        logger.error(
            "Qdrant is not reachable at {}:{}. "
            "Start it with: docker run -d -p 6333:6333 qdrant/qdrant",
            client.host,
            client.port,
        )
        return 1

    logger.info("Qdrant is available at {}:{}.", client.host, client.port)

    # ------------------------------------------------------------------
    # 2. Load documents from JSONL.
    # ------------------------------------------------------------------
    try:
        documents = load_rag_documents(args.jsonl_path)
    except FileNotFoundError as exc:
        logger.error("{}", exc)
        return 1
    except ValueError as exc:
        logger.error("Failed to parse RAG documents: {}", exc)
        return 1

    logger.info("Loaded {} RAG documents from {}.", len(documents), args.jsonl_path)

    if not documents:
        logger.warning("No documents found — nothing to upload.")
        return 0

    # ------------------------------------------------------------------
    # 3. Upload in batches.
    # ------------------------------------------------------------------
    try:
        uploaded = upload_documents(
            client, documents, batch_size=args.batch_size, dry_run=args.dry_run
        )
    except RuntimeError as exc:
        logger.error("{}", exc)
        return 1

    if args.dry_run:
        logger.info("Dry run complete — no documents written to Qdrant.")
        return 0

    logger.info("Uploaded {} / {} documents to Qdrant.", uploaded, len(documents))

    # ------------------------------------------------------------------
    # 4. Verify.
    # ------------------------------------------------------------------
    if verify_upload(client, uploaded):
        logger.info("Upload verified successfully.")
        return 0

    logger.error("Upload verification failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
