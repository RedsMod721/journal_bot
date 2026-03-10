"""Step 14b — Generate a personalised insight and persist it to the DB.

Uses the synchronous ``OllamaClient.generate_json`` interface (compatible
with the synchronous ``PipelineProcessor._run_steps`` context) to produce
a coaching insight grounded in the RAG evidence retrieved in step 06.

Graceful degradation
--------------------
- When Ollama is reported unavailable (``ollama_health["connected"] == False``),
  the step returns a static fallback immediately without calling the LLM and
  WITHOUT emitting a degraded error code — the same way the embedding step
  silently skips when Ollama is down, preserving existing test expectations.
- When Ollama is connected but the call fails (timeout, bad JSON, etc.), the
  step raises so that ``run_step(allow_degraded=True)`` records
  ``STEP_14B_INSIGHT`` in the degraded_codes and the pipeline continues.

DB writes
---------
One ``Insight`` row + one ``InsightEvidence`` row are inserted per entry.
Both are flushed inside the outer transaction, not committed independently.
The DB write always happens regardless of whether the LLM result was cached —
each entry must own its own ``Insight`` row.

Caching
-------
When a *cache* object is provided, the **LLM output only** (insight text,
category, confidence) is cached under a key derived from the entry summary
and RAG context.  DB writes are never skipped on a cache hit.  This avoids
redundant LLM calls when the same content is processed more than once (e.g.
retries) while preserving the per-entry audit trail in the database.

Cache key format: ``insight:{hash16(entry_summary + "|" + rag_context_joined)}``
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.insight import Insight, InsightEvidence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fallback constant
# ---------------------------------------------------------------------------

_FALLBACK: dict[str, Any] = {
    "insight_text": "Keep practising consistently — small daily efforts compound into remarkable results.",
    "category": "general",
    "confidence": 0.5,
}

_VALID_CATEGORIES = frozenset(
    ["skill_development", "habit_formation", "recovery", "mindset", "general"]
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_prompt(entry_summary: str, rag_context: list[str]) -> str:
    evidence_block = (
        "\n".join(f"- {c.strip()}" for c in rag_context[:3] if c.strip())
        if rag_context
        else "No prior context available."
    )
    return (
        "You are a personal development coach. "
        "Based on the user's recent activity and relevant evidence, "
        "generate one actionable, personalised insight.\n\n"
        "Return a JSON object with this EXACT structure:\n"
        '{"insight_text": "<insight, max 200 words>", '
        '"category": "<skill_development|habit_formation|recovery|mindset|general>", '
        '"confidence": <float 0.0-1.0>}\n\n'
        "Return ONLY valid JSON — no markdown, no explanation.\n\n"
        f"User's recent activity:\n{entry_summary}\n\n"
        f"Relevant evidence:\n{evidence_block}"
    )


def _insight_cache_key(entry_summary: str, rag_context: list[str]) -> str:
    """Derive a stable cache key from the LLM prompt inputs.

    Uses first 3 RAG context strings so the key reflects the actual evidence
    used in the prompt without including the full text.
    """
    context_str = "|".join(c.strip() for c in rag_context[:3] if c.strip())
    raw = f"{entry_summary}|{context_str}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"insight:{digest}"


# ---------------------------------------------------------------------------
# Public step function
# ---------------------------------------------------------------------------


def run(
    *,
    user_id: str,
    entry_id: str,
    canonical_text: str,
    rag_hits: list[dict[str, Any]],
    detection: dict[str, Any],
    ollama_health: dict[str, Any],
    ollama: Any,
    db: Session,
    cache: Any = None,
) -> dict[str, Any]:
    """Generate and persist a personalised insight for the current entry.

    Args:
        user_id:        Owning user UUID.
        entry_id:       Journal entry UUID.
        canonical_text: Normalised entry text (step 03 output).
        rag_hits:       Raw Qdrant hits from step 06.
        detection:      Signal-detection output from step 07.
        ollama_health:  Result dict from the Ollama health step (step 04).
        ollama:         OllamaClient with a sync ``generate_json(prompt)`` method.
        db:             SQLAlchemy session (write — issues flushes).
        cache:          Optional ``StepCache`` instance.  When provided, the
                        LLM-generated insight data is read from / written to
                        cache to avoid redundant Ollama calls.  DB writes are
                        always performed regardless of cache state.

    Returns:
        Dict with keys:

        ``insight_id``         — PK of the persisted Insight row.
        ``insight_text``       — The generated (or fallback) insight text.
        ``insight_category``   — Category string.
        ``insight_confidence`` — Float 0.0–1.0.
        ``from_ollama``        — True if the text came from the LLM (or cache).
        ``from_cache``         — True if the insight text was served from cache.
    """
    # Build entry summary from first 200 words + detected signals.
    words = canonical_text.split()[:200]
    entry_summary = " ".join(words)
    if detection.get("detected_skills"):
        entry_summary += (
            f"\n[Skills practised: {', '.join(detection['detected_skills'])}]"
        )

    # Extract content strings from RAG hit payloads.
    rag_context: list[str] = [
        h.get("payload", {}).get("content", "")
        for h in rag_hits
        if h.get("payload", {}).get("content")
    ]

    insight_data = _FALLBACK.copy()
    from_ollama = False
    from_cache = False

    # ── Cache read (LLM text only — DB write still happens below) ──────
    cache_key: str | None = None
    if cache is not None:
        cache_key = _insight_cache_key(entry_summary, rag_context)
        cached_llm = cache.get(cache_key)
        if cached_llm is not None:
            insight_data = cached_llm
            from_ollama = True  # cached from a prior successful LLM call
            from_cache = True
            logger.debug(
                "insights cache_hit entry_id=%s cache_key=%s", entry_id, cache_key
            )

    # ── LLM call (skipped on cache hit or when Ollama is down) ─────────
    if not from_cache and ollama_health.get("connected"):
        prompt = _build_prompt(entry_summary, rag_context)
        raw_result = ollama.generate_json(prompt)
        response_text = raw_result.get("response", "{}")
        # Strip markdown fences if present.
        cleaned = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and "insight_text" in parsed:
            category = str(parsed.get("category", "general"))
            if category not in _VALID_CATEGORIES:
                category = "general"
            try:
                confidence = float(parsed.get("confidence", 0.5))
                confidence = max(0.0, min(1.0, confidence))
            except (TypeError, ValueError):
                confidence = 0.5
            insight_data = {
                "insight_text": str(parsed["insight_text"])[:2000],
                "category": category,
                "confidence": confidence,
            }
            from_ollama = True

        # Cache the LLM output for future identical prompts.
        if from_ollama and cache is not None and cache_key is not None:
            cache.set(cache_key, insight_data)
            logger.debug(
                "insights cache_set entry_id=%s cache_key=%s", entry_id, cache_key
            )

    # ── DB write — always, so every entry has its own Insight row ──────
    insight_row = Insight(
        user_id=user_id,
        insight_type=insight_data["category"],
        title=_build_title(detection),
        description=insight_data["insight_text"],
        strength=insight_data["confidence"],
        status="active",
    )
    db.add(insight_row)
    db.flush()

    db.add(
        InsightEvidence(
            user_id=user_id,
            insight_id=insight_row.id,
            entry_id=entry_id,
            evidence_weight=1.0,
        )
    )
    db.flush()

    return {
        "insight_id": insight_row.id,
        "insight_text": insight_data["insight_text"],
        "insight_category": insight_data["category"],
        "insight_confidence": insight_data["confidence"],
        "from_ollama": from_ollama,
        "from_cache": from_cache,
    }


def _build_title(detection: dict[str, Any]) -> str:
    """Derive a short insight title from detected signals."""
    task_type = detection.get("task_type", "practice")
    skills = detection.get("detected_skills", [])
    if skills:
        return f"Session insight — {skills[0]}"
    return f"Session insight — {task_type}"
