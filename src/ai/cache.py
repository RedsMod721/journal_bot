"""Step-level caching for the AI pipeline.

Provides an in-memory LRU cache with TTL expiry and hit/miss metrics for
expensive pipeline operations (embedding, RAG search, LLM calls).

Design goals
------------
- **Zero external deps**: pure stdlib — ``collections.OrderedDict`` for LRU,
  ``hashlib`` for content-addressable keys.
- **Thread-safe reads**: single-threaded pipeline use is the primary target,
  but ``OrderedDict`` operations are GIL-protected in CPython.
- **Observable**: ``get_stats()`` exposes hit-rate, size, and eviction counts
  so operators can tune ``ttl_hours`` and ``max_size`` at runtime.
- **Backward compatible**: ``PipelineCache`` is an alias for ``StepCache`` so
  existing import sites need not change when the recommended name evolves.

Typical usage::

    cache = StepCache(ttl_hours=24, max_size=1000)

    # Key generation
    key = f"rag:{StepCache.hash_key(canonical_text)}"

    # Read-through pattern
    result = cache.get(key)
    if result is None:
        result = expensive_call()
        cache.set(key, result)

    # Observability
    stats = cache.get_stats()
    logger.info("cache hit_rate=%.2f size=%d", stats["hit_rate"], stats["size"])
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal data holder
# ---------------------------------------------------------------------------


@dataclass
class _CacheItem:
    value: Any
    expires_at: float


# ---------------------------------------------------------------------------
# StepCache
# ---------------------------------------------------------------------------


class StepCache:
    """In-memory LRU cache with per-item TTL for AI pipeline steps.

    Items are evicted by two independent policies (whichever triggers first):

    1. **TTL expiry** — any ``get`` call that finds an expired item purges it
       and returns ``None``, as if it had never been stored.
    2. **LRU capacity** — when the store reaches *max_size* entries, the
       *least-recently-used* item is evicted before the new item is inserted.

    Args:
        ttl_hours:  Time-to-live per cache entry in hours.  Default: 24.
        max_size:   Maximum number of entries before LRU eviction.  Default: 1000.

    Attributes:
        ttl_seconds: Derived TTL in seconds (``ttl_hours * 3600``).
        max_size:    Capacity limit.
    """

    def __init__(self, ttl_hours: int = 24, max_size: int = 1000) -> None:
        self.ttl_seconds: float = ttl_hours * 3600
        self.max_size: int = max_size
        self._store: OrderedDict[str, _CacheItem] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0
        logger.debug("StepCache init ttl_hours=%s max_size=%s", ttl_hours, max_size)

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any | None:
        """Return the cached value for *key*, or ``None`` on miss or expiry.

        On a hit the entry is promoted to the MRU end of the LRU order.
        Expired entries are purged lazily on access.

        Args:
            key: Cache key string.

        Returns:
            Cached value, or ``None``.
        """
        item = self._store.get(key)
        if item is None:
            self._misses += 1
            return None

        if item.expires_at <= time.time():
            del self._store[key]
            self._misses += 1
            logger.debug("cache_expired key=%s", key)
            return None

        # Promote to MRU end.
        self._store.move_to_end(key)
        self._hits += 1
        logger.debug("cache_hit key=%s", key)
        return item.value

    def set(self, key: str, value: Any) -> None:
        """Store *value* under *key*.

        When the cache is at capacity and *key* is not already present, the
        LRU (oldest-accessed) entry is evicted first.

        Args:
            key:   Cache key string.
            value: Value to cache (any picklable object).
        """
        if len(self._store) >= self.max_size and key not in self._store:
            evicted_key, _ = self._store.popitem(last=False)
            self._evictions += 1
            logger.debug("cache_evicted lru_key=%s", evicted_key)

        self._store[key] = _CacheItem(
            value=value, expires_at=time.time() + self.ttl_seconds
        )
        self._store.move_to_end(key)
        logger.debug("cache_set key=%s", key)

    def clear(self) -> None:
        """Evict all entries and reset all metrics counters."""
        self._store.clear()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        logger.info("cache_cleared")

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return a point-in-time snapshot of cache statistics.

        Returns:
            Dict with keys:

            ``hits``      — cumulative cache hits since init (or last clear).
            ``misses``    — cumulative cache misses.
            ``evictions`` — cumulative LRU evictions.
            ``hit_rate``  — float in ``[0.0, 1.0]``; 0.0 when no requests yet.
            ``size``      — current number of live entries.
            ``max_size``  — configured capacity limit.
        """
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "size": len(self._store),
            "max_size": self.max_size,
        }

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def hash_key(text: str) -> str:
        """Return a 16-hex-char content-addressable cache key component.

        Uses the first 16 characters of a SHA-256 digest — collision-resistant
        in practice for the cache sizes targeted here (max 1 000 entries).

        Args:
            text: Arbitrary string to hash (typically entry content or prompts).

        Returns:
            16-character lowercase hex string.

        Example::

            key = f"rag:{StepCache.hash_key(canonical_text)}"
        """
        return hashlib.sha256(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Back-compat alias
# ---------------------------------------------------------------------------

#: Alias kept for callers that import ``PipelineCache`` directly.
#: Prefer ``StepCache`` in new code.
PipelineCache = StepCache
