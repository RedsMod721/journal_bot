"""Step 06 — Search Qdrant for relevant RAG context.

Performs an approximate-nearest-neighbour search using the embedding vector
produced in step 05.  Returns an empty hit list when the vector is absent
(fallback embedding) so the pipeline continues without RAG context.

Caching
-------
When a *cache* object and *entry_id* are supplied, results are stored under
the key ``rag:{entry_id}`` and served from cache on subsequent calls.  Because
the embedding vector is itself deterministic per entry (step 05 caches on
``embedding:{entry_id}``), keying the RAG result on entry_id is semantically
correct: same entry → same vector → same hits.

This is particularly useful during retry / replay scenarios where the same
entry might pass through the pipeline more than once before idempotency claims
have been recorded.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def run(
    *,
    vector: list[float],
    qdrant: Any,
    cache: Any = None,
    entry_id: str = "",
) -> dict[str, Any]:
    """Search the RAG collection for documents similar to *vector*.

    Args:
        vector:    Float embedding vector from the embedding step.
                   An empty list triggers an immediate no-hit return.
        qdrant:    Qdrant adapter with ``ensure_collection()`` and
                   ``search(vector, limit)`` methods.
        cache:     Optional ``StepCache`` instance.  When provided with a
                   non-empty *entry_id*, results are read from and written to
                   the cache to avoid redundant Qdrant round-trips.
        entry_id:  Journal entry UUID — used as the cache key discriminator.
                   Ignored when *cache* is ``None``.

    Returns:
        Dict with keys:

        ``hits``       — list of raw result dicts from Qdrant.
        ``hit_count``  — ``len(hits)``.
        ``fallback``   — ``True`` when the search was skipped (empty vector).
        ``from_cache`` — ``True`` when the result was served from cache.
    """
    # Bail early on fallback vector — no Qdrant call, no cache write.
    if not vector:
        return {"hits": [], "hit_count": 0, "fallback": True, "from_cache": False}

    # Cache read.
    cache_key = f"rag:{entry_id}" if entry_id else None
    if cache is not None and cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("rag cache_hit entry_id=%s", entry_id)
            return {**cached, "from_cache": True}

    # Cache miss — perform the actual search.
    qdrant.ensure_collection()
    hits = qdrant.search(vector, limit=5)
    result = {
        "hits": hits,
        "hit_count": len(hits),
        "fallback": False,
        "from_cache": False,
    }

    # Cache write.
    if cache is not None and cache_key:
        # Store without the from_cache flag so hits/hit_count/fallback are clean.
        cache.set(cache_key, {"hits": hits, "hit_count": len(hits), "fallback": False})
        logger.debug("rag cache_set entry_id=%s hit_count=%s", entry_id, len(hits))

    return result
