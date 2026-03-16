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


def _citation_from_hit(hit: dict[str, Any]) -> dict[str, Any]:
    payload = hit.get("payload", {}) or {}
    metadata = payload.get("metadata", {}) or {}
    return {
        "doc_id": payload.get("doc_id") or hit.get("doc_id"),
        "chunk_id": metadata.get("chunk_id") or payload.get("chunk_id"),
        "title": metadata.get("title") or payload.get("title"),
        "source_type": metadata.get("source_type") or payload.get("source_type") or "rag_document",
        "locator": metadata.get("locator") or payload.get("locator"),
        "retrieved_at_utc": metadata.get("retrieved_at_utc") or payload.get("retrieved_at_utc"),
    }


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


def _prompt_inputs(
    entry_summary: str,
    rag_context: list[str],
    citations: list[dict[str, Any]],
    ollama_health: dict[str, Any],
) -> dict[str, Any]:
    return {
        "entry_summary": entry_summary,
        "rag_context": rag_context[:3],
        "citations": citations[:3],
        "ollama_connected": bool(ollama_health.get("connected")),
        "cache_key": _insight_cache_key(entry_summary, rag_context),
    }


# ---------------------------------------------------------------------------
# Public step function
# ---------------------------------------------------------------------------


def plan(
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
    """Generate a personalised insight plan for the current entry.

    Args:
        user_id:        Owning user UUID.
        entry_id:       Journal entry UUID.
        canonical_text: Normalised entry text (step 03 output).
        rag_hits:       Raw Qdrant hits from step 06.
        detection:      Signal-detection output from step 07.
        ollama_health:  Result dict from the Ollama health step (step 04).
        ollama:         OllamaClient with a sync ``generate_json(prompt)`` method.
        db:             SQLAlchemy session (read-only for plan generation).
        cache:          Optional ``StepCache`` instance.  When provided, the
                        LLM-generated insight data is read from / written to
                        cache to avoid redundant Ollama calls.  DB writes are
                        always performed regardless of cache state.

    Returns:
        Dict with keys required to persist the insight later.
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
    citations = [_citation_from_hit(hit) for hit in rag_hits][:3]

    insight_data = _FALLBACK.copy()
    from_ollama = False
    from_cache = False
    prompt_inputs = _prompt_inputs(entry_summary, rag_context, citations, ollama_health)
    suppression_reason: str | None = None
    generation_mode = "suppressed"

    # ── Cache read (LLM text only — DB write still happens below) ──────
    cache_key: str | None = None
    if cache is not None and rag_context and ollama_health.get("connected"):
        cache_key = _insight_cache_key(entry_summary, rag_context)
        cached_llm = cache.get(cache_key)
        if cached_llm is not None:
            insight_data = cached_llm
            from_ollama = True  # cached from a prior successful LLM call
            from_cache = True
            generation_mode = "llm_rag"
            logger.debug(
                "insights cache_hit entry_id=%s cache_key=%s", entry_id, cache_key
            )

    # ── LLM call (skipped on cache hit or when Ollama is down) ─────────
    if not rag_context:
        suppression_reason = "RAG_EMPTY_CONTEXT"
    elif not ollama_health.get("connected"):
        suppression_reason = "DEPENDENCY_OLLAMA_UNAVAILABLE"
    elif not from_cache:
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
            generation_mode = "llm_rag"

        # Cache the LLM output for future identical prompts.
        if from_ollama and cache is not None and cache_key is not None:
            cache.set(cache_key, insight_data)
            logger.debug(
                "insights cache_set entry_id=%s cache_key=%s", entry_id, cache_key
            )

    return {
        "user_id": user_id,
        "entry_id": entry_id,
        "generated": from_ollama,
        "persisted": False,
        "insight_text": insight_data["insight_text"] if from_ollama else "",
        "insight_category": insight_data["category"] if from_ollama else "general",
        "insight_confidence": insight_data["confidence"] if from_ollama else 0.0,
        "title": _build_title(detection),
        "from_ollama": from_ollama,
        "from_cache": from_cache,
        "citations": citations if from_ollama else [],
        "prompt_inputs": prompt_inputs,
        "generation_mode": generation_mode,
        "suppression_reason": suppression_reason,
    }


def persist_planned(
    *,
    plan: dict[str, Any],
    db: Session,
) -> dict[str, Any]:
    """Persist a previously planned insight."""
    if not plan.get("generated", False):
        return {
            "insight_id": None,
            "generated": False,
            "persisted": False,
            "insight_text": "",
            "insight_category": "general",
            "insight_confidence": 0.0,
            "from_ollama": False,
            "from_cache": bool(plan.get("from_cache")),
            "citations": [],
            "prompt_inputs": dict(plan.get("prompt_inputs", {})),
            "generation_mode": str(plan.get("generation_mode", "suppressed")),
            "suppression_reason": plan.get("suppression_reason"),
        }

    insight_row = Insight(
        user_id=plan["user_id"],
        insight_type=plan["insight_category"],
        title=plan["title"],
        description=plan["insight_text"],
        strength=plan["insight_confidence"],
        status="active",
    )
    db.add(insight_row)
    db.flush()

    db.add(
        InsightEvidence(
            user_id=plan["user_id"],
            insight_id=insight_row.id,
            entry_id=plan["entry_id"],
            evidence_weight=1.0,
        )
    )
    db.flush()

    return {
        "insight_id": insight_row.id,
        "generated": True,
        "persisted": True,
        "insight_text": plan["insight_text"],
        "insight_category": plan["insight_category"],
        "insight_confidence": plan["insight_confidence"],
        "from_ollama": bool(plan.get("from_ollama")),
        "from_cache": bool(plan.get("from_cache")),
        "citations": list(plan.get("citations", [])),
        "prompt_inputs": dict(plan.get("prompt_inputs", {})),
        "generation_mode": str(plan.get("generation_mode", "llm_rag")),
        "suppression_reason": None,
    }


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
    """Backward-compatible plan + persist helper."""
    plan_payload = plan(
        user_id=user_id,
        entry_id=entry_id,
        canonical_text=canonical_text,
        rag_hits=rag_hits,
        detection=detection,
        ollama_health=ollama_health,
        ollama=ollama,
        db=db,
        cache=cache,
    )
    return persist_planned(plan=plan_payload, db=db)


def _build_title(detection: dict[str, Any]) -> str:
    """Derive a short insight title from detected signals."""
    task_type = detection.get("task_type", "practice")
    skills = detection.get("detected_skills", [])
    if skills:
        return f"Session insight — {skills[0]}"
    return f"Session insight — {task_type}"
