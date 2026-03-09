"""Step 05 — Generate or retrieve a cached embedding vector for an entry.

Reads from a TTL cache first (keyed on entry_id) to avoid re-embedding the
same entry across retries or replays.  Raises ``RuntimeError`` when Ollama
is reported unavailable so the caller can apply a degraded fallback.
"""

from __future__ import annotations

from typing import Any


def run(
    *,
    entry_id: str,
    normalized_text: str,
    ollama_health: dict[str, Any],
    ollama: Any,
    cache: Any,
) -> dict[str, Any]:
    """Produce a float embedding vector for *normalized_text*.

    Args:
        entry_id:        Journal entry UUID — used as the cache key.
        normalized_text: Output of the normalise step (canonical_text).
        ollama_health:   Result dict from the Ollama health step.
                         Must contain ``connected`` (bool).
        ollama:          OllamaClient instance with an ``embed(text)`` method.
        cache:           StepCache instance supporting ``get`` / ``set``.

    Returns:
        Dict with keys:
            ``vector``     — list[float] embedding.
            ``from_cache`` — True when the vector was served from cache.
            ``fallback``   — True when a zero-vector fallback was used.

    Raises:
        RuntimeError: When Ollama is unavailable and no cache entry exists.
    """
    cache_key = f"embedding:{entry_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return {"vector": cached, "from_cache": True, "fallback": False}

    if not ollama_health.get("connected"):
        raise RuntimeError("ollama unavailable — cannot generate embedding")

    vector = ollama.embed(normalized_text[:4000] or f"entry:{entry_id}")
    cache.set(cache_key, vector)
    return {"vector": vector, "from_cache": False, "fallback": False}
