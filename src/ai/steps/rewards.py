"""Steps 11-13 — Quest reward computation and XP award persistence.

``compute_quest_rewards``  — step 11: convert completed-quest payloads into
                             final XP amounts using the canonical integer pipeline.
``persist_skill_awards``   — step 12: insert XpAward rows for skill XP, guarded
                             by the award_identity_key dedup mechanism.
``persist_theme_awards``   — step 13: derive and insert theme XpAward rows from
                             each skill award, with the same dedup guard.

All three functions are idempotent: a second call with identical arguments
(same user_id / entry_id / quest_id / ruleset_version) produces no new rows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.core.xp import (
    build_skill_award_identity_key,
    build_theme_award_identity_key,
    derive_theme_awards_from_skill_award,
    finalize_quest_xp,
)
from src.db.models.skill import SkillThemeMapping
from src.db.models.xp import XpAward


# ---------------------------------------------------------------------------
# Step 11
# ---------------------------------------------------------------------------


def compute_quest_rewards(
    *,
    completed_quests: list[dict[str, Any]],
    variety_multiplier_bp: int = 10000,
    troll_bp: int = 10000,
    diminishing_bp: int = 10000,
) -> dict[str, Any]:
    """Convert completed-quest payloads to final XP amounts.

    Runs each quest's base_xp through ``finalize_quest_xp`` using the
    variety, troll, and diminishing-returns multipliers computed in steps
    08a/08b/08c.  All default to 10 000 bp (1.0×) for backward compatibility
    when the upstream steps are absent or degraded.

    Args:
        completed_quests:      List of dicts with keys ``quest_id``,
                               ``skill_id``, ``base_xp``.
        variety_multiplier_bp: Basis-point variety bonus from step 08a
                               (default 10 000 = no bonus).
        troll_bp:              Basis-point troll multiplier from step 08b
                               (default 10 000 = 1.0×).
        diminishing_bp:        Basis-point diminishing-returns multiplier
                               from step 08c (default 10 000 = 1.0×, range
                               7500–10 000).

    Returns:
        Dict with key ``rewards`` — list of dicts:
            ``quest_id``, ``skill_id``, ``quest_xp`` (final int XP).
    """
    rewards: list[dict[str, Any]] = []
    for quest in completed_quests:
        breakdown = finalize_quest_xp(
            quest_xp_total=int(quest["base_xp"]),
            troll_bp=troll_bp,
            variety_multiplier_bp=variety_multiplier_bp,
            arc_reward_multiplier_bp=10000,
            diminishing_bp=diminishing_bp,
            penalty_xp=0,
        )
        rewards.append(
            {
                "quest_id": quest["quest_id"],
                "skill_id": quest["skill_id"],
                "quest_xp": breakdown["final_xp"],
            }
        )
    return {"rewards": rewards}


# ---------------------------------------------------------------------------
# Step 12
# ---------------------------------------------------------------------------


def persist_skill_awards(
    *,
    user_id: str,
    entry_id: str,
    processing_run_id: str,
    rewards: list[dict[str, Any]],
    db: Session,
    pipeline_version: str,
    ruleset_version: str,
) -> dict[str, Any]:
    """Insert idempotent XpAward rows for skill XP.

    Uses ``build_skill_award_identity_key`` to derive a deterministic SHA-256
    key per award.  Existing rows with a matching key are returned as-is
    (``replayed: True``) without inserting duplicates.

    Args:
        user_id:            Owning user UUID.
        entry_id:           Journal entry UUID.
        processing_run_id:  UUID of the current processing run (audit trail).
        rewards:            Output of ``compute_quest_rewards``.
        db:                 SQLAlchemy session (write — issues flushes).
        pipeline_version:   Pinned pipeline version string (e.g. "week3-v1").
        ruleset_version:    Pinned ruleset version string (e.g. "s10-v8").

    Returns:
        Dict with key ``skill_awards`` — list of persisted award dicts:
            ``award_id``, ``skill_id``, ``quest_id``, ``amount``,
            ``identity_key``, ``replayed``.
    """
    persisted: list[dict[str, Any]] = []

    for reward in rewards:
        identity_key = build_skill_award_identity_key(
            user_id=user_id,
            entry_id=entry_id,
            quest_id=reward["quest_id"],
            xp_reason="quest_complete",
            distribution_type="primary",
            skill_id=reward["skill_id"],
            ruleset_version=ruleset_version,
        )
        existing = (
            db.query(XpAward)
            .filter(
                XpAward.user_id == user_id,
                XpAward.award_identity_key == identity_key,
            )
            .one_or_none()
        )
        if existing is not None:
            persisted.append(
                {
                    "award_id": existing.id,
                    "skill_id": existing.skill_id,
                    "quest_id": existing.quest_id,
                    "amount": existing.amount,
                    "identity_key": identity_key,
                    "replayed": True,
                }
            )
            continue

        row = XpAward(
            user_id=user_id,
            entry_id=entry_id,
            xp_reason="quest_complete",
            processing_run_id=processing_run_id,
            award_identity_key=identity_key,
            ruleset_version=ruleset_version,
            pipeline_version=pipeline_version,
            skill_id=reward["skill_id"],
            theme_id=None,
            quest_id=reward["quest_id"],
            amount=int(reward["quest_xp"]),
            distribution_type="primary",
            skill_weight=1.0,
            source_skill_id=None,
            source_skill_xp=None,
        )
        db.add(row)
        db.flush()
        persisted.append(
            {
                "award_id": row.id,
                "skill_id": row.skill_id,
                "quest_id": row.quest_id,
                "amount": row.amount,
                "identity_key": identity_key,
                "replayed": False,
            }
        )

    return {"skill_awards": persisted}


# ---------------------------------------------------------------------------
# Step 13
# ---------------------------------------------------------------------------


def persist_theme_awards(
    *,
    user_id: str,
    entry_id: str,
    processing_run_id: str,
    skill_awards: list[dict[str, Any]],
    db: Session,
    pipeline_version: str,
    ruleset_version: str,
) -> dict[str, Any]:
    """Derive and insert theme XpAward rows from persisted skill awards.

    For each skill award the function looks up the skill's theme mappings,
    apportions 0.1% of the skill XP across the linked themes, and inserts
    one XpAward row per theme — again guarded by ``award_identity_key``.

    Args:
        user_id:            Owning user UUID.
        entry_id:           Journal entry UUID.
        processing_run_id:  Current processing run UUID.
        skill_awards:       Output of ``persist_skill_awards``.
        db:                 SQLAlchemy session (write — issues flushes).
        pipeline_version:   Pinned pipeline version string.
        ruleset_version:    Pinned ruleset version string.

    Returns:
        Dict with key ``theme_awards`` — list of persisted award dicts:
            ``award_id``, ``theme_id``, ``amount``, ``identity_key``,
            ``replayed``.
    """
    persisted: list[dict[str, Any]] = []

    for skill_award in skill_awards:
        skill_id = skill_award.get("skill_id")
        if not skill_id:
            continue

        mappings: list[SkillThemeMapping] = (
            db.query(SkillThemeMapping)
            .filter(
                SkillThemeMapping.user_id == user_id,
                SkillThemeMapping.skill_id == skill_id,
            )
            .all()
        )
        if not mappings:
            continue

        # Equal-weight apportionment; last bucket absorbs rounding remainder.
        bp = int(10000 / len(mappings))
        weights: list[tuple[str, int]] = [(m.theme_id, bp) for m in mappings]
        weights[-1] = (weights[-1][0], 10000 - bp * (len(mappings) - 1))

        derived = derive_theme_awards_from_skill_award(
            # Theme propagation is 0.1% of skill XP (architecture §10).
            source_skill_xp=max(1, int(int(skill_award["amount"]) * 0.001)),
            source_skill_id=str(skill_id),
            theme_weights_bp=weights,
        )

        for t_award in derived:
            identity_key = build_theme_award_identity_key(
                user_id=user_id,
                entry_id=entry_id,
                quest_id=skill_award["quest_id"],
                xp_reason="quest_complete",
                distribution_type="theme",
                theme_id=str(t_award["theme_id"]),
                source_skill_id=str(t_award.get("source_skill_id")),
                source_skill_xp=int(t_award.get("source_skill_xp") or 0),
                ruleset_version=ruleset_version,
            )
            existing = (
                db.query(XpAward)
                .filter(
                    XpAward.user_id == user_id,
                    XpAward.award_identity_key == identity_key,
                )
                .one_or_none()
            )
            if existing is not None:
                persisted.append(
                    {
                        "award_id": existing.id,
                        "theme_id": existing.theme_id,
                        "amount": existing.amount,
                        "identity_key": identity_key,
                        "replayed": True,
                    }
                )
                continue

            row = XpAward(
                user_id=user_id,
                entry_id=entry_id,
                xp_reason="quest_complete",
                processing_run_id=processing_run_id,
                award_identity_key=identity_key,
                ruleset_version=ruleset_version,
                pipeline_version=pipeline_version,
                skill_id=None,
                theme_id=str(t_award["theme_id"]),
                quest_id=skill_award["quest_id"],
                amount=int(t_award["amount"]),
                distribution_type="theme",
                skill_weight=None,
                source_skill_id=str(t_award.get("source_skill_id")),
                source_skill_xp=int(t_award.get("source_skill_xp") or 0),
            )
            db.add(row)
            db.flush()
            persisted.append(
                {
                    "award_id": row.id,
                    "theme_id": row.theme_id,
                    "amount": row.amount,
                    "identity_key": identity_key,
                    "replayed": False,
                }
            )

    return {"theme_awards": persisted}
