"""Step 06 — Search Qdrant for relevant RAG context.

Performs an approximate-nearest-neighbour search using the embedding vector
produced in step 05.  Returns an empty hit list when the vector is absent
(fallback embedding) so the pipeline continues without RAG context.
"""

from __future__ import annotations

from typing import Any


def run(*, vector: list[float], qdrant: Any) -> dict[str, Any]:
    """Search the RAG collection for documents similar to *vector*.

    Args:
        vector: Float embedding vector from the embedding step.
                An empty list triggers an immediate no-hit return.
        qdrant: Qdrant adapter with ``ensure_collection()`` and
                ``search(vector, limit)`` methods.

    Returns:
        Dict with keys:
            ``hits``      — list of raw result dicts from Qdrant.
            ``hit_count`` — len(hits).
            ``fallback``  — True when the search was skipped.
    """
    if not vector:
        return {"hits": [], "hit_count": 0, "fallback": True}

    qdrant.ensure_collection()
    hits = qdrant.search(vector, limit=5)
    return {"hits": hits, "hit_count": len(hits), "fallback": False}
