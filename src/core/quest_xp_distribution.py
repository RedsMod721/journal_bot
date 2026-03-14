"""
Quest XP distribution and apportionment.

Implements Section 10.6 (XP Awarding and Distribution Q22) from architecture.

Multiplier chain (Section 10.6.2 — basis-point arithmetic):
    T1 = floor(quest_xp_total * troll_bp / 10000)        # Anomaly
    T2 = floor(T1 * variety_bp / 10000)                  # Balance
    T3 = floor(T2 * arc_bp / 10000)                      # Story Arc
    final_xp = max(0, T3 - penalty_xp)

Apportionment (Section 10.6.4 — Huntington-Hill):
    Initial: floor(total_xp * weight_bp / sum_bp) per skill
    Remainder: priority = weight_bp / sqrt(n * (n+1))
    Tie-break: lexicographic min skill_id

Primary skill (Section 10.6.4):
    min(skill_id) among skills with maximum weight_bp

Idempotency (Section 10.6.5):
    award_identity_key = SHA-256(user_id:entry_id:quest_id:xp_reason:distribution_type:skill_id)
    Protected by uq_xp_awards_identity unique constraint.
"""
from __future__ import annotations

import hashlib
import math
import uuid
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.models.xp import XpAward


class QuestXPDistributionService:
    """
    Deterministic XP distribution across skills following Section 10.6.

    Responsibilities:
        - Multiplier chain (troll → variety → arc → penalty)
        - Huntington-Hill apportionment (exact sum guarantee)
        - Primary skill labelling
        - Idempotent XP award persistence
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Section 10.6.2 — Multiplier chain
    # ------------------------------------------------------------------

    def calculate_final_xp(
        self,
        quest_xp_total: int,
        troll_multiplier_bp: int = 10000,
        variety_multiplier_bp: int = 10000,
        arc_reward_multiplier_bp: int = 10000,
        penalty_xp: int = 0,
    ) -> int:
        """
        Apply the basis-point multiplier chain then subtract penalty.

        Multiplier order (Section 10.6.2):
            1. Anomaly (troll)
            2. Balance (variety)
            3. Story Arc

        Args:
            quest_xp_total: Base quest XP (480 for instant quests).
            troll_multiplier_bp: Anomaly troll multiplier in basis points
                (10000 = ×1.0).
            variety_multiplier_bp: Balance variety bonus in basis points.
            arc_reward_multiplier_bp: Story arc reward multiplier in basis
                points.
            penalty_xp: Non-negative XP penalty subtracted after multipliers
                (Q23 graduated failure penalty).

        Returns:
            Final XP, clamped to >= 0.
        """
        T1 = math.floor(quest_xp_total * troll_multiplier_bp / 10000)
        T2 = math.floor(T1 * variety_multiplier_bp / 10000)
        T3 = math.floor(T2 * arc_reward_multiplier_bp / 10000)
        return max(0, T3 - penalty_xp)

    # ------------------------------------------------------------------
    # Section 10.6.4 — Huntington-Hill apportionment
    # ------------------------------------------------------------------

    def apportion_xp(
        self,
        total_xp: int,
        skills_weights_bp: Dict[str, int],
    ) -> Dict[str, int]:
        """
        Distribute XP across skills using Huntington-Hill apportionment.

        Algorithm (Section 10.6.4):
            1. Floor allocation: floor(total_xp * weight_bp / sum_bp) per skill.
            2. Remainder distribution, one XP at a time:
               - Priority = weight_bp / sqrt(n * (n + 1))  [inf when n == 0]
               - Tie-break: lexicographic min skill_id (ascending)

        Guarantees:
            sum(result.values()) == total_xp  (exact, no rounding loss)
            Deterministic: identical inputs always produce identical outputs.

        Args:
            total_xp: Total XP to distribute (>= 0).
            skills_weights_bp: {skill_id: weight_bp}. All weights must be > 0.

        Returns:
            {skill_id: xp_amount} with sum == total_xp.

        Raises:
            ValueError: if weights map is empty or sums to zero.
        """
        if not skills_weights_bp or sum(skills_weights_bp.values()) == 0:
            raise ValueError(
                "skills_weights_bp must be non-empty with a positive total weight"
            )

        if total_xp == 0:
            return {sid: 0 for sid in skills_weights_bp}

        sum_bp = sum(skills_weights_bp.values())
        awards: Dict[str, int] = {}
        remainder = total_xp

        # Step 1: floor allocation — sorted for deterministic initial state
        for skill_id in sorted(skills_weights_bp):
            allocated = math.floor(total_xp * skills_weights_bp[skill_id] / sum_bp)
            awards[skill_id] = allocated
            remainder -= allocated

        # Step 2: distribute remainder using Huntington-Hill seat priority
        while remainder > 0:
            winner = min(
                awards.keys(),
                key=lambda sid: (
                    # Ascending -priority → highest priority wins
                    -(
                        skills_weights_bp[sid] / math.sqrt(awards[sid] * (awards[sid] + 1))
                        if awards[sid] > 0
                        else float("inf")
                    ),
                    sid,  # Lexicographic min as tie-break
                ),
            )
            awards[winner] += 1
            remainder -= 1

        assert sum(awards.values()) == total_xp, (
            f"Apportionment invariant violated: got {sum(awards.values())}, "
            f"expected {total_xp}"
        )
        return awards

    # ------------------------------------------------------------------
    # Section 10.6.4 — Primary skill selection
    # ------------------------------------------------------------------

    def select_primary_skill(self, skills_weights_bp: Dict[str, int]) -> str:
        """
        Select the primary skill for distribution_type labelling.

        Primary = min(skill_id) among skills with maximum weight_bp.
        Deterministic: when a single skill has the highest weight it is
        always chosen; ties broken by lexicographic min UUID.

        Args:
            skills_weights_bp: {skill_id: weight_bp}

        Returns:
            Primary skill_id.

        Raises:
            ValueError: if the map is empty.
        """
        if not skills_weights_bp:
            raise ValueError("skills_weights_bp cannot be empty")
        max_weight = max(skills_weights_bp.values())
        candidates = [s for s, w in skills_weights_bp.items() if w == max_weight]
        return min(candidates)

    # ------------------------------------------------------------------
    # Section 10.6.5 — Idempotent persistence
    # ------------------------------------------------------------------

    def persist_xp_awards(
        self,
        user_id: str,
        entry_id: str,
        quest_id: str,
        skill_awards: Dict[str, int],
        skills_weights_bp: Dict[str, int],
        xp_reason: str,
        processing_run_id: str,
        quest_matcher_version: int,
    ) -> List[XpAward]:
        """
        Write XP award rows to the database, idempotently (Section 10.6.5).

        Rules enforced:
            - amount > 0 — zero awards are silently skipped.
            - Skill XOR theme — skill_id set, theme_id null (skill rows only).
            - distribution_type: 'primary' for the primary skill, 'secondary'
              for all others.
            - Idempotency via award_identity_key (SHA-256 of canonical fields)
              protected by the uq_xp_awards_identity unique constraint.

        On an IntegrityError (duplicate award_identity_key) the method rolls
        back to a savepoint, fetches the existing row, and returns it — making
        the call safe to retry within the same pipeline run.

        Args:
            user_id: User receiving XP.
            entry_id: Source journal entry ID.
            quest_id: Completed quest ID.
            skill_awards: {skill_id: amount} from apportion_xp.
            skills_weights_bp: {skill_id: weight_bp} used for weight storage.
            xp_reason: Stable reason key (e.g. 'quest_instant_complete').
            processing_run_id: Pipeline run identifier for audit trail.
            quest_matcher_version: Quest matcher schema version (audit).

        Returns:
            List of XpAward objects (newly created or pre-existing).
        """
        primary_skill = self.select_primary_skill(skills_weights_bp)
        now = datetime.now(timezone.utc)
        now_ms = int(now.timestamp() * 1000)
        persisted: List[XpAward] = []

        for skill_id, amount in skill_awards.items():
            if amount <= 0:
                continue  # Section 10.6.5: never write zero-amount rows

            distribution_type = "primary" if skill_id == primary_skill else "secondary"
            identity_key = _identity_key(
                user_id, entry_id, quest_id, xp_reason, distribution_type, skill_id
            )
            weight_bp = skills_weights_bp.get(skill_id, 0)

            award = XpAward(
                id=str(uuid.uuid4()),
                user_id=user_id,
                entry_id=entry_id,
                quest_id=quest_id,
                xp_reason=xp_reason,
                distribution_type=distribution_type,
                amount=amount,
                skill_id=skill_id,
                theme_id=None,
                skill_weight=weight_bp / 10000,  # 0–1 float for legacy column
                skill_weight_bp=weight_bp,
                source_skill_id=None,
                source_skill_xp=None,
                processing_run_id=processing_run_id,
                quest_matcher_version=quest_matcher_version,
                awarded_at=now,
                awarded_at_utc_ms=now_ms,
                award_identity_key=identity_key,
            )

            # Use a savepoint so a duplicate key rolls back only this row
            sp = self.db.begin_nested()
            try:
                self.db.add(award)
                self.db.flush()
                sp.commit()
                persisted.append(award)
            except IntegrityError:
                sp.rollback()
                existing = (
                    self.db.query(XpAward)
                    .filter(XpAward.award_identity_key == identity_key)
                    .first()
                )
                if existing:
                    persisted.append(existing)

        return persisted


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _identity_key(
    user_id: str,
    entry_id: str,
    quest_id: str,
    xp_reason: str,
    distribution_type: str,
    skill_id: str,
) -> str:
    """
    Deterministic award identity hash (Section 10.6.5).

    SHA-256 over the canonical colon-joined fields that uniquely identify
    one skill award within a processing run.
    """
    raw = ":".join(
        [user_id, entry_id, quest_id, xp_reason, distribution_type, skill_id]
    )
    return hashlib.sha256(raw.encode()).hexdigest()
