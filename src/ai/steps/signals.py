"""Step 07 — Detect skills, activities, emotions, energy, and task type.

Operates entirely on the normalised canonical text; no Ollama call required.
Skill detection is token-intersection against the user's existing Skill rows.
All other signals use keyword lists that can be extended without touching the
orchestrator.

Extending signals
-----------------
To add a new activity keyword, append to ``_ACTIVITY_KEYWORDS``.
To add a new emotion, append to ``_EMOTION_KEYWORDS``.
To add a new task-type branch, add an ``elif`` block to ``_classify_task_type``.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.skill import Skill

# ---------------------------------------------------------------------------
# Keyword registries (module-level constants for easy extension/testing)
# ---------------------------------------------------------------------------

_ACTIVITY_KEYWORDS: list[str] = [
    "run",
    "study",
    "code",
    "write",
    "read",
    "workout",
    "meditate",
    "walk",
    "practice",
    "build",
]

_EMOTION_KEYWORDS: list[str] = [
    "happy",
    "sad",
    "angry",
    "anxious",
    "calm",
    "excited",
]

_CREATIVE_TOKENS: frozenset[str] = frozenset(["draw", "paint", "design", "compose"])
_PHYSICAL_TOKENS: frozenset[str] = frozenset(["run", "lift", "swim", "walk"])
_SOCIAL_TOKENS: frozenset[str] = frozenset(["talk", "friend", "team", "meeting"])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify_task_type(lowered: str) -> str:
    if any(t in lowered for t in _CREATIVE_TOKENS):
        return "creative"
    if any(t in lowered for t in _PHYSICAL_TOKENS):
        return "physical"
    if any(t in lowered for t in _SOCIAL_TOKENS):
        return "social"
    return "analytical"


def _estimate_energy(lowered: str) -> int:
    if "exhausted" in lowered or "drained" in lowered:
        return 3
    if "energized" in lowered or "great" in lowered:
        return 8
    return 5


# ---------------------------------------------------------------------------
# Public step function
# ---------------------------------------------------------------------------


def run(*, user_id: str, canonical_text: str, db: Session) -> dict[str, Any]:
    """Detect structured signals from *canonical_text*.

    Performs a single DB query to load the user's skills; all other
    detection is pure string matching with no further I/O.

    Args:
        user_id:        Owning user UUID — used to scope the Skill query.
        canonical_text: Normalised entry text from the normalise step.
        db:             SQLAlchemy session (read-only within this step).

    Returns:
        Dict with keys:
            ``detected_skills``      — sorted list of matched skill names.
            ``detected_activities``  — sorted list of matched activity keywords.
            ``dominant_emotions``    — list of matched emotion keywords.
            ``energy_level``         — int 1-10.
            ``self_compassion_score``— int 1-10.
            ``task_type``            — one of: analytical, creative, physical, social.
    """
    lowered = canonical_text.lower()
    words = set(re.findall(r"[a-zA-Z][a-zA-Z0-9_\-']*", lowered))

    # Skill detection: token-intersection match against user's skill roster.
    skills: list[Skill] = db.query(Skill).filter(Skill.user_id == user_id).all()
    detected_skills: list[str] = []
    for skill in skills:
        tokens = set(skill.canonical_name.lower().split())
        if tokens and tokens.intersection(words):
            detected_skills.append(skill.name)

    detected_activities = sorted([kw for kw in _ACTIVITY_KEYWORDS if kw in lowered])
    dominant_emotions = [e for e in _EMOTION_KEYWORDS if e in lowered]
    self_compassion_score = 3 if "hate myself" in lowered else 7

    return {
        "detected_skills": sorted(set(detected_skills)),
        "detected_activities": detected_activities,
        "dominant_emotions": dominant_emotions,
        "energy_level": _estimate_energy(lowered),
        "self_compassion_score": self_compassion_score,
        "task_type": _classify_task_type(lowered),
    }
