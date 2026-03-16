"""
Journal entry skill hierarchy processing.

Standalone function that combines discovery, XP distribution, skill
activation, and unlock evaluation into a single pass over affected skills.

Flow
----
1. Discover LOCKED skills referenced in the entry (→ DISCOVERED).
2. Distribute XP with hierarchy redirection (locked skills) and spillage
   (activated ancestors), using XPDistributionService.
3. Apply the merged XP distribution to Skill rows.
4. Activate any UNLOCKED_HIDDEN skill that received XP (first-gain rule).
5. Batch-evaluate all skills for state transitions triggered by a parent
   crossing the Lv20 (Rank D) threshold.

Usage
-----
    from src.core.journal_hierarchy import process_journal_entry_with_hierarchy

    results = process_journal_entry_with_hierarchy(
        user_id=user_id,
        entry_id=entry_id,
        skill_xp_awards={"skill_physical_running": 1000, ...},
        db=db,
    )
"""
from __future__ import annotations

import logging
from typing import Dict, List

from sqlalchemy.orm import Session

from src.core.enums import SkillState
from src.core.skill_unlocks import SkillUnlockService
from src.core.xp_distribution import XPDistributionService

logger = logging.getLogger(__name__)


def process_journal_entry_with_hierarchy(
    user_id: str,
    entry_id: str,
    skill_xp_awards: Dict[str, int],
    db: Session,
) -> Dict:
    """
    Process a journal entry through the full skill hierarchy system.

    Args:
        user_id:         Owning user UUID.
        entry_id:        Journal entry UUID — used as the discovery source tag.
        skill_xp_awards: ``{source_skill_id: base_xp}`` mapping of raw XP
                         awards before hierarchy distribution.
        db:              SQLAlchemy session (writes committed inside services).

    Returns:
        Dict with keys:
            discoveries          — list of ``{skill_id, canonical_name}`` for
                                   skills that were LOCKED and are now DISCOVERED.
            xp_distributions     — ``{source_skill_id: xp_awarded}`` after
                                   redirection and spillage.
            xp_results           — ``{source_skill_id: {old_xp, new_xp,
                                   old_level, new_level, xp_gained}}``
            activations          — list of ``{skill_id, canonical_name}`` for
                                   UNLOCKED_HIDDEN skills just activated.
            unlocks              — list of state transition dicts from the
                                   batch evaluation (locked→unlocked_hidden,
                                   discovered→activated).
            total_skills_affected — count of skills that received XP.
    """
    unlock_service = SkillUnlockService(db)
    xp_service = XPDistributionService(db)

    discoveries: List[Dict] = []
    merged_distribution: Dict[str, int] = {}
    activations: List[Dict] = []

    # ------------------------------------------------------------------
    # Step 1 — Discover LOCKED skills referenced in the entry
    # ------------------------------------------------------------------
    for source_skill_id in skill_xp_awards:
        state = unlock_service.get_or_create_skill_state(user_id, source_skill_id)
        if state is None:
            logger.debug(
                "No GlobalSkill row for %r — skipping discovery.", source_skill_id
            )
            continue

        if state.state == SkillState.LOCKED:
            unlock_service.discover_skill(
                user_id, source_skill_id, f"entry:{entry_id}"
            )
            skill_info = unlock_service.hierarchy.get(source_skill_id, {})
            discoveries.append(
                {
                    "skill_id": source_skill_id,
                    "canonical_name": skill_info.get(
                        "canonical_name", source_skill_id
                    ),
                }
            )
            logger.debug("Discovered skill %r for user %s.", source_skill_id, user_id)

    # ------------------------------------------------------------------
    # Step 2 — Calculate XP distribution (redirection + spillage)
    # ------------------------------------------------------------------
    for source_skill_id, base_xp in skill_xp_awards.items():
        if base_xp <= 0:
            continue
        distribution = xp_service.distribute_xp(user_id, source_skill_id, base_xp)
        for sid, xp in distribution.items():
            merged_distribution[sid] = merged_distribution.get(sid, 0) + xp

    # ------------------------------------------------------------------
    # Step 3 — Apply merged distribution to Skill rows
    # ------------------------------------------------------------------
    xp_results = xp_service.apply_xp_distribution(user_id, merged_distribution)

    # ------------------------------------------------------------------
    # Step 4 — Activate UNLOCKED_HIDDEN skills that gained XP
    #
    # Re-read state post-distribution: apply_xp_distribution may have
    # already triggered child unlocks via _check_children_unlocks.
    # ------------------------------------------------------------------
    for source_skill_id in skill_xp_awards:
        if source_skill_id not in merged_distribution:
            # XP was fully redirected away from this skill — no activation.
            continue
        state = unlock_service.get_or_create_skill_state(user_id, source_skill_id)
        if state is None:
            continue
        if state.state == SkillState.UNLOCKED_HIDDEN:
            unlock_service.activate_skill(user_id, source_skill_id)
            skill_info = unlock_service.hierarchy.get(source_skill_id, {})
            activations.append(
                {
                    "skill_id": source_skill_id,
                    "canonical_name": skill_info.get(
                        "canonical_name", source_skill_id
                    ),
                }
            )
            logger.debug("Activated skill %r for user %s.", source_skill_id, user_id)

    # ------------------------------------------------------------------
    # Step 5 — Batch-evaluate all skills for pending state transitions
    #
    # Catches children that are now unlockable because a parent just
    # crossed the Lv20 (Rank D) threshold.
    # ------------------------------------------------------------------
    all_transitions = unlock_service.evaluate_all_skills(user_id)

    meaningful_unlocks = [
        t
        for t in all_transitions
        if t["old_state"] in (SkillState.LOCKED, SkillState.DISCOVERED)
        and t["new_state"] in (SkillState.UNLOCKED_HIDDEN, SkillState.ACTIVATED)
    ]

    if meaningful_unlocks:
        logger.info(
            "entry:%s — %d new skill unlock(s) for user %s.",
            entry_id,
            len(meaningful_unlocks),
            user_id,
        )

    logger.info(
        "[pipeline:hierarchy] entry=%s user=%s source_awards=%s discoveries=%d "
        "merged_distribution=%s activations=%d unlocks=%d",
        entry_id,
        user_id,
        skill_xp_awards,
        len(discoveries),
        merged_distribution,
        len(activations),
        len(meaningful_unlocks),
    )
    if skill_xp_awards and not merged_distribution:
        logger.warning(
            "[pipeline:hierarchy] entry=%s user=%s produced no XP distribution from "
            "source awards=%s",
            entry_id,
            user_id,
            skill_xp_awards,
        )

    return {
        "discoveries": discoveries,
        "xp_distributions": merged_distribution,
        "xp_results": xp_results,
        "activations": activations,
        "unlocks": meaningful_unlocks,
        "total_skills_affected": len(merged_distribution),
    }
