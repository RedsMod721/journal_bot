"""Step 14 — Update skill and theme XP progression counters.

Increments ``Skill.xp`` and ``Theme.xp`` for every non-replayed award
produced in steps 12-13, then flushes so the updated values are visible
within the current transaction.

Replayed awards (``replayed: True``) are skipped to preserve idempotency:
re-running the same processing run must not double-count XP.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.skill import Skill, Theme


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def update_counters(
    *,
    skill_awards: list[dict[str, Any]],
    theme_awards: list[dict[str, Any]],
    db: Session,
) -> dict[str, Any]:
    """Increment XP on Skill and Theme rows for fresh (non-replayed) awards.

    Args:
        skill_awards: Output of ``rewards.persist_skill_awards``.
        theme_awards: Output of ``rewards.persist_theme_awards``.
        db:           SQLAlchemy session (write — issues a flush).

    Returns:
        Dict with keys:
            ``updated_skills`` — number of Skill rows whose XP was incremented.
            ``updated_themes`` — number of Theme rows whose XP was incremented.
    """
    skill_updates = 0
    theme_updates = 0

    for award in skill_awards:
        if award.get("replayed"):
            continue
        skill: Skill | None = (
            db.query(Skill).filter(Skill.id == award["skill_id"]).one_or_none()
        )
        if skill is None:
            continue
        skill.xp = int(skill.xp) + int(award["amount"])
        skill.last_activity_at = _now_utc()
        skill_updates += 1

    for award in theme_awards:
        if award.get("replayed"):
            continue
        theme: Theme | None = (
            db.query(Theme).filter(Theme.id == award["theme_id"]).one_or_none()
        )
        if theme is None:
            continue
        theme.xp = int(theme.xp) + int(award["amount"])
        theme_updates += 1

    db.flush()
    return {"updated_skills": skill_updates, "updated_themes": theme_updates}
