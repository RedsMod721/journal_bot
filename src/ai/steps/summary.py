"""Step 15 — Assemble the human-readable pipeline result summary.

Aggregates counts from the signal-detection, quest-progress, and XP-award
steps into a single flat dict that is embedded in the final pipeline result
payload and consumed by API clients.
"""

from __future__ import annotations

from typing import Any


def build(
    *,
    rag_hits: list[dict[str, Any]],
    detection: dict[str, Any],
    progress: dict[str, Any],
    skill_awards: dict[str, Any],
    theme_awards: dict[str, Any],
    variety: dict[str, Any] | None = None,
    anomaly: dict[str, Any] | None = None,
    insight: dict[str, Any] | None = None,
    detected_strategies: list[str] | None = None,
    strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the result summary dict.

    Args:
        rag_hits:             Raw hit list from the RAG search step.
        detection:            Output of the signals step.
        progress:             Output of ``quests.update_progress``.
        skill_awards:         Output of ``rewards.persist_skill_awards``.
        theme_awards:         Output of ``rewards.persist_theme_awards``.
        variety:              Output of step 08a (optional).
        anomaly:              Output of step 08b/14c (optional).
        insight:              Output of step 14b (optional).
        detected_strategies:  List of credited strategy names from step 08c (optional).

    Returns:
        Flat dict with core and extension fields.
    """
    return {
        # Core — always present
        "detected_skills": detection["detected_skills"],
        "detected_activities": detection["detected_activities"],
        "rag_hit_count": len(rag_hits),
        "matched_quest_count": int(progress["matched_quest_count"]),
        "completed_quest_count": len(progress["completed_quest_ids"]),
        "skill_award_count": len(skill_awards["skill_awards"]),
        "theme_award_count": len(theme_awards["theme_awards"]),
        # Extensions — defaults when corresponding steps are absent/degraded
        "variety_multiplier_bp": (variety or {}).get("variety_multiplier_bp", 10000),
        "variety_score": (variety or {}).get("variety_score", 0.0),
        "troll_multiplier": (anomaly or {}).get("troll_multiplier", 1.0),
        "insight_text": (insight or {}).get("insight_text", ""),
        "anomaly_score": (anomaly or {}).get("anomaly_score", 0.0),
        "detected_strategies": detected_strategies or [],
        "diminishing_multiplier": (strategy or {}).get("diminishing_multiplier", 1.0),
    }
