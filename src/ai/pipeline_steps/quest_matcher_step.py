"""
Quest matcher pipeline step.

Implements Section 10 integration into Section 13 pipeline.

This step runs after the entry is marked completed (step_16p) so that
``QuestMatcherService.match_quests_for_entry`` sees ``entry.status == 'completed'``.
It operates within the outer ``_apply_tx_b`` transaction — callers must NOT call
``db.commit()`` on the shared session; a ``db.flush()`` is used instead so the
awards are visible within the transaction before the pipeline commits.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy.orm import Session

from src.core.arc_lifecycle import ArcLifecycleService
from src.core.quest_matcher import QuestMatcherService
from src.core.quest_theme_derivation import ThemeXPDerivationService
from src.core.quest_theme_mapping import ThemeMapping
from src.core.quest_xp_distribution import QuestXPDistributionService
from src.db.models.journal_entry import JournalEntry
from src.db.models.user import User

if TYPE_CHECKING:
    from src.db.models.quest import Quest
    from src.db.models.xp import XpAward

logger = logging.getLogger(__name__)

# Quest matcher version — bump when matching/distribution logic changes.
QUEST_MATCHER_VERSION = 10


class QuestMatcherStep:
    """Quest matcher pipeline step (Section 10).

    Designed to be instantiated once per pipeline run inside ``_apply_tx_b``.
    All DB writes are flushed (not committed) so the outer transaction remains
    the single commit boundary.
    """

    def __init__(
        self,
        db: Session,
        theme_mapping_path: str = "data/seeds/matcher/theme_mapping_v1.json",
        templates_path: str = "data/seeds/matcher/quest_templates_v1.json",
    ) -> None:
        self.db = db
        self.quest_matcher = QuestMatcherService(db, templates_path=templates_path)
        self.xp_dist = QuestXPDistributionService(db)

        self.theme_mapping = ThemeMapping(theme_mapping_path)
        logger.debug(
            "QuestMatcherStep: theme_mapping hash=%s",
            self.theme_mapping.get_file_hash(),
        )

        self.theme_derivation = ThemeXPDerivationService(db, self.theme_mapping)
        self.arc_lifecycle = ArcLifecycleService(db)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        user: User,
        entry: JournalEntry,
        structured_data: dict,
        troll_multiplier_bp: int,
        variety_multiplier_bp: int,
        processing_run_id: str,
    ) -> Dict:
        """Execute the quest matcher step (Step 7 in conceptual pipeline order).

        Must be called AFTER ``entry.status`` has been set to ``'completed'``
        (i.e. after step_16p) because ``QuestMatcherService`` enforces this
        precondition.

        Args:
            user:                  User model instance.
            entry:                 Completed JournalEntry — status must be
                                   ``'completed'``.
            structured_data:       Dict from ``_planned_structured_data`` (contains
                                   ``skills_weights_bp``, etc.).
            troll_multiplier_bp:   Anomaly troll multiplier in basis points
                                   (from step_08b / step_16b).
            variety_multiplier_bp: Variety bonus in basis points
                                   (from step_08a / step_16d).
            processing_run_id:     Pipeline run identifier for audit trail.

        Returns:
            Dict with keys::

                instant_quest  — Quest ORM object or None.
                streak_quests  — list[Quest].
                xp_awards      — list[XpAward] (skill + theme awards).
                total_xp_awarded — int.
                notes          — list[str] (diagnostic notes from matcher).

            On hard failure (eligibility / entry-time missing) an ``'error'``
            key is also present and the award lists are empty.
        """
        logger.info(
            "QuestMatcherStep.execute: entry=%s user=%s", entry.id, user.id
        )

        # -- Arc multipliers ---------------------------------------------
        active_arc = self.arc_lifecycle.get_active_arc(user.id)
        arc_requirement_multiplier_bp: int = (
            int(active_arc.xp_requirement_multiplier_bp)
            if active_arc is not None
            else 10000
        )
        arc_reward_multiplier_bp: int = (
            int(active_arc.xp_reward_multiplier_bp)
            if active_arc is not None
            else 10000
        )

        # -- 1. Match quests (Section 10.5) -------------------------------
        match_result = self.quest_matcher.match_quests_for_entry(
            user=user,
            entry=entry,
            structured_data=structured_data,
            requirement_multiplier_bp=arc_requirement_multiplier_bp,
        )

        if "error" in match_result:
            logger.error(
                "QuestMatcherStep: matching failed entry=%s error=%s",
                entry.id,
                match_result["error"],
            )
            return {
                "error": match_result["error"],
                "instant_quest": None,
                "streak_quests": [],
                "created_quests": [],
                "progressed_quests": [],
                "completed_quests": [],
                "xp_awards": [],
                "total_xp_awarded": 0,
                "notes": match_result.get("notes", []),
            }

        instant_quest: Optional["Quest"] = match_result["instant_quest"]
        streak_quests: List["Quest"] = match_result.get("streak_quests", [])
        created_quests: List["Quest"] = match_result.get("created_quests", [])
        progressed_quests: List["Quest"] = match_result.get("progressed_quests", [])
        completed_quests: List["Quest"] = match_result.get("completed_quests", [])
        notes: List[str] = match_result.get("notes", [])

        # -- 2. XP calculation and distribution ---------------------------
        xp_awards: List["XpAward"] = []
        total_xp: int = 0

        for completed_quest in completed_quests:
            quest_xp_total: int = int(completed_quest.base_xp or 480)

            final_xp = self.xp_dist.calculate_final_xp(
                quest_xp_total=quest_xp_total,
                troll_multiplier_bp=troll_multiplier_bp,
                variety_multiplier_bp=variety_multiplier_bp,
                arc_reward_multiplier_bp=arc_reward_multiplier_bp,
                penalty_xp=0,  # Penalties handled separately (Section 10.6.3)
            )
            total_xp += final_xp

            skills_weights_bp: dict = structured_data.get("skills_weights_bp", {}) or {}
            # Filter out non-positive weights before distributing
            skills_weights_bp = {
                k: v for k, v in skills_weights_bp.items() if isinstance(v, int) and v > 0
            }
            if completed_quest.skill_id and completed_quest.skill_id not in skills_weights_bp:
                skills_weights_bp = {completed_quest.skill_id: 10000}

            xp_reason = f"quest_{completed_quest.completion_type}_complete"
            if skills_weights_bp and sum(skills_weights_bp.values()) > 0:
                # Huntington-Hill apportionment across skills (Section 10.6.4)
                skill_awards_dict = self.xp_dist.apportion_xp(final_xp, skills_weights_bp)

                skill_award_rows = self.xp_dist.persist_xp_awards(
                    user_id=user.id,
                    entry_id=entry.id,
                    quest_id=completed_quest.id,
                    skill_awards=skill_awards_dict,
                    skills_weights_bp=skills_weights_bp,
                    xp_reason=xp_reason,
                    processing_run_id=processing_run_id,
                    quest_matcher_version=QUEST_MATCHER_VERSION,
                )
                xp_awards.extend(skill_award_rows)

                # Theme XP derivation (Section 10.7.3)
                theme_award_rows = self.theme_derivation.derive_theme_awards(
                    user_id=user.id,
                    entry_id=entry.id,
                    quest_id=completed_quest.id,
                    skill_awards=skill_award_rows,
                    xp_reason=xp_reason,
                    processing_run_id=processing_run_id,
                    quest_matcher_version=QUEST_MATCHER_VERSION,
                )
                xp_awards.extend(theme_award_rows)

            else:
                # No valid weights — fall back to single skill
                fallback_skill_id = self.quest_matcher._get_fallback_skill(user.id)
                if fallback_skill_id:
                    fallback_weights = {fallback_skill_id: 10000}
                    skill_awards_dict = {fallback_skill_id: final_xp}

                    skill_award_rows = self.xp_dist.persist_xp_awards(
                        user_id=user.id,
                        entry_id=entry.id,
                        quest_id=completed_quest.id,
                        skill_awards=skill_awards_dict,
                        skills_weights_bp=fallback_weights,
                        xp_reason=xp_reason,
                        processing_run_id=processing_run_id,
                        quest_matcher_version=QUEST_MATCHER_VERSION,
                    )
                    xp_awards.extend(skill_award_rows)
                else:
                    logger.warning(
                        "QuestMatcherStep: no fallback skill for user=%s, "
                        "skipping XP award persist",
                        user.id,
                    )
                    notes.append("NO_FALLBACK_SKILL")

        # Flush within the outer transaction — no commit.
        self.db.flush()

        logger.info(
            "QuestMatcherStep complete: entry=%s instant=%s streaks=%d "
            "completed=%d created=%d progressed=%d xp_awards=%d total_xp=%d",
            entry.id,
            instant_quest.id if instant_quest else None,
            len(streak_quests),
            len(completed_quests),
            len(created_quests),
            len(progressed_quests),
            len(xp_awards),
            total_xp,
        )

        return {
            "instant_quest": instant_quest,
            "streak_quests": streak_quests,
            "created_quests": created_quests,
            "progressed_quests": progressed_quests,
            "completed_quests": completed_quests,
            "xp_awards": xp_awards,
            "total_xp_awarded": total_xp,
            "notes": notes,
        }
