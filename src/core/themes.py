"""
Theme utilities for canonical 12-theme handling.

This module centralizes:
1) canonical theme names + descriptions
2) user theme pre-seeding (idempotent)
3) skill->theme mapping backfill/repair from GlobalSkill.related_themes_json
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from sqlalchemy.orm import Session

from src.core.enums import get_rank_from_level
from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill, SkillThemeMapping, Theme


CANONICAL_THEME_DESCRIPTIONS: dict[str, str] = {
    "Physical": "Exercise, health, sports, physical activities",
    "Mental": "Learning, cognition, mindfulness, mental health",
    "Professional": "Work, career, job skills, income",
    "Social": "Relationships, networking, communication",
    "Creative": "Art, music, writing, crafts, creativity",
    "Emotional": "Self-awareness, therapy, emotional regulation",
    "Practical": "Life admin, chores, errands, maintenance",
    "Intellectual": "Study, research, philosophy, deep thinking",
    "Spiritual": "Meditation, faith, meaning, purpose",
    "Adventure": "Travel, exploration, novelty, trying new things",
    "Discipline": "Habits, consistency, grit, self-control",
    "Rest": "Sleep, leisure, recovery, relaxation",
}

CANONICAL_THEME_NAMES: tuple[str, ...] = tuple(CANONICAL_THEME_DESCRIPTIONS.keys())
_CANONICAL_THEME_LOOKUP = {
    name.casefold(): name for name in CANONICAL_THEME_NAMES
}
_CANONICAL_THEME_INDEX = {name: idx for idx, name in enumerate(CANONICAL_THEME_NAMES)}


def canonicalize_theme_name(theme_name: str | None) -> str | None:
    """Return canonical theme name for *theme_name*, or None if unsupported."""
    if theme_name is None:
        return None
    cleaned = str(theme_name).strip()
    if not cleaned:
        return None
    return _CANONICAL_THEME_LOOKUP.get(cleaned.casefold())


def theme_sort_key(theme_name: str) -> int:
    """Deterministic sort index for canonical themes."""
    return _CANONICAL_THEME_INDEX.get(theme_name, len(_CANONICAL_THEME_INDEX))


def ensure_user_themes(db: Session, user_id: str) -> dict[str, Theme]:
    """
    Ensure the user has one row for each canonical base theme.

    Idempotent: only inserts missing themes, never duplicates existing rows.
    """
    existing_rows: list[Theme] = (
        db.query(Theme)
        .filter(Theme.user_id == user_id, Theme.name.in_(CANONICAL_THEME_NAMES))
        .all()
    )
    existing_by_name = {row.name: row for row in existing_rows}

    for theme_name in CANONICAL_THEME_NAMES:
        if theme_name in existing_by_name:
            continue
        row = Theme(
            user_id=user_id,
            name=theme_name,
            description=CANONICAL_THEME_DESCRIPTIONS[theme_name],
            level=1,
            rank=get_rank_from_level(1).value,
            xp=0,
        )
        db.add(row)
        existing_by_name[theme_name] = row

    db.flush()

    # Ensure rows added in this session have materialized IDs.
    refreshed_rows: list[Theme] = (
        db.query(Theme)
        .filter(Theme.user_id == user_id, Theme.name.in_(CANONICAL_THEME_NAMES))
        .all()
    )
    return {row.name: row for row in refreshed_rows}


def _parse_related_theme_names(raw_json: str | None) -> list[str]:
    if not raw_json:
        return []
    try:
        parsed = json.loads(raw_json)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    names: list[str] = []
    for item in parsed:
        canonical = canonicalize_theme_name(str(item))
        if canonical is not None:
            names.append(canonical)
    # keep deterministic order and uniqueness
    return sorted(set(names), key=theme_sort_key)


def ensure_skill_theme_mappings(
    db: Session,
    user_id: str,
    skill_ids: Iterable[str],
) -> int:
    """
    Ensure skill-theme mappings exist for the provided user skill IDs.

    Mappings are derived from GlobalSkill.related_themes_json and only canonical
    theme names are accepted.

    Returns:
        Number of SkillThemeMapping rows inserted.
    """
    deduped_skill_ids = sorted({str(skill_id) for skill_id in skill_ids if skill_id})
    if not deduped_skill_ids:
        return 0

    themes_by_name = ensure_user_themes(db, user_id)

    skills: list[Skill] = (
        db.query(Skill)
        .filter(
            Skill.user_id == user_id,
            Skill.id.in_(deduped_skill_ids),
            Skill.global_skill_id.isnot(None),
        )
        .all()
    )
    if not skills:
        return 0

    global_skill_ids = sorted({str(skill.global_skill_id) for skill in skills if skill.global_skill_id})
    global_theme_json_by_id: dict[str, str | None] = {}
    if global_skill_ids:
        for row in (
            db.query(GlobalSkill.id, GlobalSkill.related_themes_json)
            .filter(GlobalSkill.id.in_(global_skill_ids))
            .all()
        ):
            global_theme_json_by_id[str(row.id)] = row.related_themes_json

    existing_pairs = {
        (row.skill_id, row.theme_id)
        for row in (
            db.query(SkillThemeMapping.skill_id, SkillThemeMapping.theme_id)
            .filter(
                SkillThemeMapping.user_id == user_id,
                SkillThemeMapping.skill_id.in_(deduped_skill_ids),
            )
            .all()
        )
    }

    created_count = 0
    for skill in sorted(skills, key=lambda item: item.id):
        related_theme_names = _parse_related_theme_names(
            global_theme_json_by_id.get(str(skill.global_skill_id))
        )
        for theme_name in related_theme_names:
            theme_row = themes_by_name.get(theme_name)
            if theme_row is None:
                continue
            pair = (skill.id, theme_row.id)
            if pair in existing_pairs:
                continue
            db.add(
                SkillThemeMapping(
                    user_id=user_id,
                    skill_id=skill.id,
                    theme_id=theme_row.id,
                )
            )
            existing_pairs.add(pair)
            created_count += 1

    if created_count:
        db.flush()

    return created_count
