"""Step 14 — Update skill and theme XP progression counters.

When ``user_id`` is supplied the function routes skill XP through the
hierarchy-aware ``XPDistributionService`` (redirection to parents for
locked/discovered skills, spillage to activated ancestors).  Discovery,
activation, and batch unlock evaluation are handled inside
``process_journal_entry_with_hierarchy``.

When ``user_id`` is *not* supplied (or a skill row has no ``global_skill_id``)
the function falls back to the original direct-increment path so the pipeline
remains backward-compatible in degraded/test environments.

Replayed awards (``replayed: True``) are skipped in all paths to preserve
idempotency.  Theme XP is always applied via direct increment (themes have no
hierarchy).
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.core.enums import get_rank_from_level
from src.core.xp import calculate_level_from_xp
from src.db.models.skill import Skill, Theme

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _direct_skill_update(skill: Skill, amount: int) -> None:
    """Apply XP directly to a Skill row (legacy / no-hierarchy path)."""
    skill.xp = int(skill.xp) + amount
    skill.level = calculate_level_from_xp(int(skill.xp))
    skill.rank = get_rank_from_level(int(skill.level)).value
    skill.last_activity_at = _now_utc()


def update_counters(
    *,
    skill_awards: list[dict[str, Any]],
    theme_awards: list[dict[str, Any]],
    db: Session,
    user_id: Optional[str] = None,
    entry_id: Optional[str] = None,
) -> dict[str, Any]:
    """Increment XP on Skill and Theme rows for fresh (non-replayed) awards.

    Args:
        skill_awards: Output of ``rewards.persist_skill_awards``.
        theme_awards: Output of ``rewards.persist_theme_awards``.
        db:           SQLAlchemy session (write — issues a flush).
        user_id:      When provided, routes skill XP through the hierarchy
                      distribution service instead of direct increment.
        entry_id:     Journal entry UUID forwarded as the discovery source tag.

    Returns:
        Dict with keys:
            ``updated_skills`` — number of Skill rows whose XP was incremented.
            ``updated_themes`` — number of Theme rows whose XP was incremented.

        When hierarchy routing is active the dict also includes the keys
        returned by ``process_journal_entry_with_hierarchy``:
            ``discoveries``, ``xp_distributions``, ``xp_results``,
            ``activations``, ``unlocks``, ``total_skills_affected``.
    """
    theme_updates = 0
    hierarchy_meta: dict[str, Any] = {}
    direct_skill_updates = 0
    source_xp: dict[str, int] = {}
    legacy_awards: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Skill XP — hierarchy-aware path (user_id required)
    # ------------------------------------------------------------------
    if user_id is not None:
        from src.db.models.global_kb import GlobalSkill
        from src.core.journal_hierarchy import process_journal_entry_with_hierarchy

        for award in skill_awards:
            if award.get("replayed"):
                continue

            skill: Skill | None = (
                db.query(Skill).filter(Skill.id == award["skill_id"]).one_or_none()
            )
            if skill is None:
                continue

            if skill.global_skill_id is None:
                legacy_awards.append(award)
                continue

            global_skill: GlobalSkill | None = (
                db.query(GlobalSkill)
                .filter(GlobalSkill.id == skill.global_skill_id)
                .one_or_none()
            )
            if global_skill is None or global_skill.source_skill_id is None:
                legacy_awards.append(award)
                continue

            source_xp[global_skill.source_skill_id] = (
                source_xp.get(global_skill.source_skill_id, 0) + int(award["amount"])
            )

        if source_xp:
            hierarchy_meta = process_journal_entry_with_hierarchy(
                user_id=user_id,
                entry_id=entry_id or "",
                skill_xp_awards=source_xp,
                db=db,
            )

        # Legacy fallback — skills that have no global_skill_id
        for award in legacy_awards:
            skill = db.query(Skill).filter(Skill.id == award["skill_id"]).one_or_none()
            if skill is None:
                continue
            _direct_skill_update(skill, int(award["amount"]))
            direct_skill_updates += 1

    # ------------------------------------------------------------------
    # Skill XP — legacy direct path (no user_id / backward compat)
    # ------------------------------------------------------------------
    else:
        for award in skill_awards:
            if award.get("replayed"):
                continue
            skill = db.query(Skill).filter(Skill.id == award["skill_id"]).one_or_none()
            if skill is None:
                continue
            _direct_skill_update(skill, int(award["amount"]))
            direct_skill_updates += 1

    # ------------------------------------------------------------------
    # Theme XP — always direct (themes have no hierarchy)
    # ------------------------------------------------------------------
    for award in theme_awards:
        if award.get("replayed"):
            continue
        theme: Theme | None = (
            db.query(Theme).filter(Theme.id == award["theme_id"]).one_or_none()
        )
        if theme is None:
            continue
        theme.xp = int(theme.xp) + int(award["amount"])
        theme.level = calculate_level_from_xp(int(theme.xp))
        theme.rank = get_rank_from_level(int(theme.level)).value
        theme_updates += 1

    db.flush()

    updated_skills = (
        hierarchy_meta.get("total_skills_affected", 0) + direct_skill_updates
    )
    result = {
        "updated_skills": updated_skills,
        "updated_themes": theme_updates,
        **hierarchy_meta,
    }
    logger.info(
        "[pipeline:progression] entry=%s user=%s skill_awards=%d theme_awards=%d "
        "hierarchy_sources=%s legacy_awards=%d updated_skills=%d updated_themes=%d",
        entry_id,
        user_id,
        len(skill_awards),
        len(theme_awards),
        source_xp,
        len(legacy_awards),
        updated_skills,
        theme_updates,
    )
    if user_id is not None and skill_awards and not source_xp and not legacy_awards:
        logger.warning(
            "[pipeline:progression] entry=%s user=%s received skill awards but none could "
            "be mapped into hierarchy or legacy progression payloads",
            entry_id,
            user_id,
        )
    return result
