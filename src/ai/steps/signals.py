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

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.skill import Skill

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword registries (module-level constants for easy extension/testing)
# ---------------------------------------------------------------------------

_ACTIVITY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("run", ("run", "runs", "ran", "running", "jog", "jogging", "sprint")),
    (
        "study",
        (
            "study",
            "studied",
            "studying",
            "flashcard",
            "lecture",
            "tutorial",
            "course",
            "research",
            "review",
        ),
    ),
    (
        "code",
        ("code", "coded", "coding", "programming", "python", "javascript", "debug"),
    ),
    ("write", ("write", "wrote", "writing", "draft", "drafted", "journaled")),
    ("read", ("read", "reading", "book", "article", "chapter")),
    (
        "workout",
        ("workout", "exercise", "exercised", "exercising", "gym", "training session"),
    ),
    (
        "pushup",
        ("pushup", "pushups", "push-up", "push-ups", "push up", "push ups"),
    ),
    (
        "strength_training",
        (
            "strength training",
            "resistance training",
            "weights",
            "lifting",
            "lifted",
            "barbell",
            "dumbbell",
        ),
    ),
    ("meditate", ("meditate", "meditated", "meditation", "mindfulness", "breathing")),
    ("walk", ("walk", "walked", "walking", "hike", "hiking", "stroll", "strolled")),
    ("practice", ("practice", "practiced", "practise", "practised", "drill")),
    ("build", ("build", "built", "ship", "shipped", "create", "created")),
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
_PHYSICAL_TOKENS: frozenset[str] = frozenset(
    [
        "run",
        "lift",
        "swim",
        "walk",
        "workout",
        "exercise",
        "pushup",
        "strength training",
        "weights",
    ]
)
_SOCIAL_TOKENS: frozenset[str] = frozenset(["talk", "friend", "team", "meeting"])
_PHYSICAL_ACTIVITY_KEYS: frozenset[str] = frozenset(
    ["run", "workout", "pushup", "strength_training", "walk"]
)
_LEARNING_ACTIVITY_KEYS: frozenset[str] = frozenset(["study", "read", "code"])
_UNMAPPED_ACTIVITY_HINTS: dict[str, tuple[str, ...]] = {
    "exercise": ("exercise", "exercising"),
    "gym": ("gym",),
    "pushup": ("pushup", "pushups", "push-up", "push-ups", "push up", "push ups"),
    "strength_training": (
        "strength training",
        "resistance training",
        "lifting",
        "lifted",
        "weights",
    ),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify_task_type(lowered: str, detected_activities: list[str]) -> str:
    activity_set = set(detected_activities)
    if any(t in lowered for t in _CREATIVE_TOKENS):
        return "creative"
    if activity_set.intersection(_PHYSICAL_ACTIVITY_KEYS) or any(
        t in lowered for t in _PHYSICAL_TOKENS
    ):
        return "physical"
    if activity_set.intersection(_LEARNING_ACTIVITY_KEYS):
        return "intellectual"
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

    detected_activities = [
        activity
        for activity, markers in _ACTIVITY_PATTERNS
        if any(marker in lowered for marker in markers)
    ]
    dominant_emotions = [e for e in _EMOTION_KEYWORDS if e in lowered]
    self_compassion_score = 3 if "hate myself" in lowered else 7
    unmapped_hints = sorted(
        hint
        for hint, keywords in _UNMAPPED_ACTIVITY_HINTS.items()
        if any(keyword in lowered for keyword in keywords)
    )

    result = {
        "detected_skills": sorted(set(detected_skills)),
        "detected_activities": detected_activities,
        "dominant_emotions": dominant_emotions,
        "energy_level": _estimate_energy(lowered),
        "self_compassion_score": self_compassion_score,
        "task_type": _classify_task_type(lowered, detected_activities),
    }
    logger.info(
        "[pipeline:signals] user=%s roster=%d detected_skills=%s detected_activities=%s "
        "task_type=%s energy=%s unmapped_hints=%s",
        user_id,
        len(skills),
        result["detected_skills"],
        result["detected_activities"],
        result["task_type"],
        result["energy_level"],
        unmapped_hints,
    )
    if unmapped_hints and not result["detected_skills"]:
        logger.warning(
            "[pipeline:signals] user=%s found activity hints without user skill matches "
            "hints=%s roster_preview=%s",
            user_id,
            unmapped_hints,
            [skill.canonical_name for skill in skills[:8]],
        )
    if unmapped_hints and not result["detected_activities"]:
        logger.warning(
            "[pipeline:signals] user=%s found raw activity hints that did not map into "
            "detected_activities hints=%s",
            user_id,
            unmapped_hints,
        )
    return result
