"""
Harmony dimension classification.

Implements Section 6.3 (Dimension Scoring) from architecture.

Precedence (§6.3.3):
  1. task_type  → TASKTYPE_TO_DIMS lookup
  2. skills_themes_involved JSON → THEME_TO_DIM lookup (via Theme.name)
  3. keyword fallback on entry content
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Set

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from src.db.models.journal_entry import JournalEntry, JournalEntryStructured

# ---------------------------------------------------------------------------
# Canonical mappings (§6.3.5)
# ---------------------------------------------------------------------------

TASKTYPE_TO_DIMS: dict[str, list[str]] = {
    "physical": ["physical"],
    "workout": ["physical"],
    "analytical": ["mental", "productivity"],
    "intellectual": ["mental", "growth"],
    "social": ["social"],
    "creative": ["creative"],
    "practical": ["productivity"],
    "administrative": ["productivity"],
    "rest": ["rest"],
    "recovery": ["rest"],
    "sleep": ["rest"],
    "nap": ["rest"],
}

THEME_TO_DIM: dict[str, str] = {
    "physical": "physical",
    "mental": "mental",
    "social": "social",
    "rest": "rest",
    "creative": "creative",
    "professional": "productivity",
    "practical": "productivity",
    "discipline": "growth",
    "intellectual": "growth",
    "adventure": "growth",
    "emotional": "mental",
    "spiritual": "mental",
}

SKILL_CANON_TO_DIM: dict[str, str] = {
    "cardio": "physical",
    "running": "physical",
    "swimming": "physical",
    "cycling": "physical",
    "strength_training": "physical",
    "weightlifting": "physical",
    "yoga": "physical",
    "pilates": "physical",
    "stretching": "physical",
    "cooking": "physical",
    "meditation": "mental",
    "mindfulness": "mental",
    "reading": "mental",
    "study": "mental",
    "problem_solving": "mental",
    "critical_thinking": "mental",
    "therapy": "mental",
    "self_reflection": "mental",
    "communication": "social",
    "conversation": "social",
    "networking": "social",
    "socializing": "social",
    "empathy": "social",
    "active_listening": "social",
    "community_service": "social",
    "programming": "productivity",
    "coding": "productivity",
    "writing": "productivity",
    "documentation": "productivity",
    "project_management": "productivity",
    "sleep_quality": "rest",
    "leisure_activities": "rest",
    "gaming": "rest",
    "entertainment": "rest",
    "relaxation_techniques": "rest",
    "journaling": "growth",
    "goal_setting": "growth",
    "planning": "growth",
    "personal_development": "growth",
    "drawing": "creative",
    "painting": "creative",
    "music": "creative",
    "composition": "creative",
    "creative_writing": "creative",
    "design": "creative",
    "crafting": "creative",
}

# Conservative keyword sets for the fallback tier (§6.3.7)
_KEYWORDS: dict[str, list[str]] = {
    "physical": ["workout", "exercise", "run", "gym", "hike", "swim"],
    "mental": ["meditate", "think", "analyze", "reflect", "journal"],
    "social": ["meeting", "social", "friend", "family", "conversation"],
    "productivity": ["work", "project", "code", "write", "build", "task"],
    "rest": ["sleep", "rest", "relax", "nap", "recharge"],
    "growth": ["learn", "study", "read", "course", "practice", "skill"],
    "creative": ["draw", "paint", "create", "design", "compose", "craft"],
}


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class HarmonyClassifier:
    """Classify journal entries into the 7 harmony dimensions.

    Usage::

        classifier = HarmonyClassifier(db)
        dims = classifier.classify_dimensions(entry, structured)
        # → frozenset of dimension names, e.g. {"physical", "growth"}
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def classify_dimensions(
        self,
        entry: "JournalEntry",
        structured: "JournalEntryStructured",
    ) -> Set[str]:
        """Return the set of dimensions addressed by this entry.

        Applies 3-tier precedence — returns on first non-empty result.
        """
        # Tier 1: task_type
        if structured.task_type:
            dims = self._from_task_type(structured.task_type)
            if dims:
                return dims

        # Tier 2: skills/themes JSON
        if structured.skills_themes_involved:
            dims = self._from_skills_themes(
                structured.skills_themes_involved, entry.user_id
            )
            if dims:
                return dims

        # Tier 3: keyword fallback
        return self._from_keywords(entry.content or "")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _from_task_type(self, task_type: str) -> Set[str]:
        key = task_type.strip().lower()
        mapping = TASKTYPE_TO_DIMS.get(key)
        return set(mapping) if mapping else set()

    def _from_skills_themes(self, skills_themes_json: str, user_id: str) -> Set[str]:
        try:
            raw_items = json.loads(skills_themes_json)
        except (ValueError, TypeError):
            return set()

        items = raw_items if isinstance(raw_items, list) else []
        dims: Set[str] = set()
        from src.db.models.skill import Skill, SkillThemeMapping, Theme

        normalized_items: list[dict[str, str]] = []
        for item in items:
            if isinstance(item, str):
                normalized_items.append({"kind": "unknown", "id": item})
            elif isinstance(item, dict) and isinstance(item.get("id"), str):
                normalized_items.append(
                    {"kind": str(item.get("kind") or "unknown"), "id": item["id"]}
                )

        theme_ids = [item["id"] for item in normalized_items if item["kind"] == "theme"]
        if theme_ids:
            themes = (
                self._db.query(Theme)
                .filter(Theme.user_id == user_id, Theme.id.in_(theme_ids))
                .all()
            )
            for theme in themes:
                dim = THEME_TO_DIM.get(theme.name.strip().casefold())
                if dim:
                    dims.add(dim)

        skill_ids = [item["id"] for item in normalized_items if item["kind"] == "skill"]
        if skill_ids:
            mappings = (
                self._db.query(SkillThemeMapping, Theme)
                .join(
                    Theme,
                    (Theme.user_id == SkillThemeMapping.user_id)
                    & (Theme.id == SkillThemeMapping.theme_id),
                )
                .filter(
                    SkillThemeMapping.user_id == user_id,
                    SkillThemeMapping.skill_id.in_(skill_ids),
                )
                .all()
            )
            mapped_skill_ids: Set[str] = set()
            for mapping, theme in mappings:
                mapped_skill_ids.add(mapping.skill_id)
                dim = THEME_TO_DIM.get(theme.name.strip().casefold())
                if dim:
                    dims.add(dim)

            fallback_skills = (
                self._db.query(Skill)
                .filter(Skill.user_id == user_id, Skill.id.in_(skill_ids))
                .all()
            )
            for skill in fallback_skills:
                if skill.id in mapped_skill_ids:
                    continue
                dim = SKILL_CANON_TO_DIM.get((skill.canonical_name or "").strip().casefold())
                if dim:
                    dims.add(dim)

        return dims

    def _from_keywords(self, content: str) -> Set[str]:
        tokens = set(filter(None, re.split(r"[^0-9A-Za-z_]+", content.casefold())))
        return {
            dim
            for dim, keywords in _KEYWORDS.items()
            if any(kw in tokens for kw in keywords)
        }
