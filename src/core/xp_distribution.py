"""
XP distribution logic with redirection (locked/discovered skills) and spillage
(activated skills).

Terminology matches skill_unlocks.py:
    source_skill_id — string key from the hierarchy JSONL (e.g. "skill_physical_running")
    global_id       — UUID primary key of GlobalSkill, used for DB FK lookups

Distribution rules:
    Rule 1  — Locked / Discovered: redirect all XP up to parents (split equally);
              recurse until XP reaches an activated skill.
    Rule 2  — Activated / UNLOCKED_HIDDEN: full XP + spillage to ancestors
              (L-1 +20%, L-2 +10%, L-3 +5%, L-4 +2.5%).
    Rule 2b — If an ancestor is locked/discovered: halve spillage, redirect
              halved amount to that ancestor's parents.
    Rule 3  — User-blocked: treated identically to locked (Rule 1).
    Rule 4  — Cannot block Lv20+ skills (enforced upstream; not checked here).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

from src.core.enums import SkillState, get_rank_from_level
from src.core.skill_unlocks import SkillUnlockService
from src.core.xp import calculate_level_from_xp, calculate_xp_for_level  # noqa: F401 (re-exported)
from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill

_UNLOCK_LEVEL = 20  # Rank D threshold — reaching this triggers child unlocks

# Spillage percentages for ancestor levels L-1 through L-4
_SPILLAGE_PCTS = [0.20, 0.10, 0.05, 0.025]


def _can_receive_xp(state: Optional[object]) -> bool:
    """Return True if a skill state object can accept XP directly."""
    if state is None:
        return False
    return (
        state.state in (SkillState.ACTIVATED, SkillState.UNLOCKED_HIDDEN)
        and not state.user_blocked
    )


class XPDistributionService:
    """
    Distribute XP to skills according to the hierarchy unlock rules.

    Public interface:
        distribute_xp(user_id, source_skill_id, base_xp)
            → Dict[source_skill_id, xp_to_award]

        apply_xp_distribution(user_id, distribution)
            → Dict[source_skill_id, {old_xp, new_xp, old_level, new_level, xp_gained}]
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.unlock_service = SkillUnlockService(db)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def distribute_xp(
        self,
        user_id: str,
        source_skill_id: str,
        base_xp: int,
    ) -> Dict[str, int]:
        """
        Calculate XP distribution for one skill award.

        Args:
            user_id:         The user receiving XP.
            source_skill_id: Hierarchy key of the skill that triggered the award.
            base_xp:         Raw XP amount before distribution.

        Returns:
            Mapping of source_skill_id → XP amount to award.
        """
        if base_xp <= 0:
            return {}

        state = self.unlock_service.get_or_create_skill_state(user_id, source_skill_id)

        # Rules 1 & 3: redirect
        if state is None or state.user_blocked or state.state in (
            SkillState.LOCKED,
            SkillState.DISCOVERED,
        ):
            return self._redirect_xp(user_id, source_skill_id, base_xp)

        # Rule 2: full XP + spillage
        distribution: Dict[str, int] = {source_skill_id: base_xp}
        spillage = self._calculate_spillage(user_id, source_skill_id, base_xp)
        for sid, xp in spillage.items():
            distribution[sid] = distribution.get(sid, 0) + xp

        return distribution

    # ------------------------------------------------------------------
    # Redirection (Rules 1, 3)
    # ------------------------------------------------------------------

    def _redirect_xp(
        self,
        user_id: str,
        source_skill_id: str,
        xp_amount: int,
        visited: Optional[Set[str]] = None,
    ) -> Dict[str, int]:
        """
        Redirect XP upward through the hierarchy until it reaches a skill
        that can receive XP directly.  Uses recursion with cycle detection.
        """
        if xp_amount <= 0:
            return {}

        if visited is None:
            visited = set()

        if source_skill_id in visited:
            return {}
        # Keep cycle detection path-local. A shared mutable "visited" set across
        # sibling recursion branches can incorrectly suppress valid alternate
        # routes and silently drop XP.
        path_visited = set(visited)
        path_visited.add(source_skill_id)

        skill_info = self.unlock_service.hierarchy.get(source_skill_id)
        if not skill_info:
            return {}

        parent_ids: List[str] = skill_info.get("parent_skill_ids", [])
        if not parent_ids:
            # Root skill with no parents — XP cannot propagate further
            return {}

        # Split evenly; integer division floors each portion; the remainder is
        # distributed to the first parents (deterministic ordering).
        n = len(parent_ids)
        base_share = xp_amount // n
        remainder = xp_amount - base_share * n

        distribution: Dict[str, int] = {}

        for i, parent_id in enumerate(parent_ids):
            share = base_share + (1 if i < remainder else 0)
            if share <= 0:
                continue

            parent_state = self.unlock_service.get_or_create_skill_state(
                user_id, parent_id
            )

            if _can_receive_xp(parent_state):
                distribution[parent_id] = distribution.get(parent_id, 0) + share
            else:
                # Parent is also blocked/locked/discovered — keep going up
                sub = self._redirect_xp(user_id, parent_id, share, path_visited)
                for sid, xp in sub.items():
                    distribution[sid] = distribution.get(sid, 0) + xp

        return distribution

    # ------------------------------------------------------------------
    # Spillage (Rule 2 / 2b)
    # ------------------------------------------------------------------

    def _calculate_spillage(
        self,
        user_id: str,
        source_skill_id: str,
        base_xp: int,
    ) -> Dict[str, int]:
        """
        Calculate ancestor spillage for an activated skill.

        For each ancestor tier (L-1 through L-4):
          - If the ancestor can receive XP directly → add spillage_xp.
          - If the ancestor is locked/discovered/blocked (Rule 2b):
              halve the spillage and redirect the halved amount upward.
        """
        spillage: Dict[str, int] = {}
        ancestors_by_level = self._get_ancestors_by_level(source_skill_id, max_levels=4)

        for level_diff, ancestor_ids in enumerate(ancestors_by_level, start=1):
            spillage_pct = _SPILLAGE_PCTS[level_diff - 1]
            spillage_xp = int(base_xp * spillage_pct)
            if spillage_xp <= 0:
                continue

            for ancestor_id in ancestor_ids:
                ancestor_state = self.unlock_service.get_or_create_skill_state(
                    user_id, ancestor_id
                )

                if _can_receive_xp(ancestor_state):
                    spillage[ancestor_id] = spillage.get(ancestor_id, 0) + spillage_xp
                else:
                    # Rule 2b: halve and redirect
                    halved = spillage_xp // 2
                    if halved <= 0:
                        continue
                    redirected = self._redirect_xp(user_id, ancestor_id, halved)
                    for sid, xp in redirected.items():
                        spillage[sid] = spillage.get(sid, 0) + xp

        return spillage

    def _get_ancestors_by_level(
        self,
        source_skill_id: str,
        max_levels: int = 4,
    ) -> List[List[str]]:
        """
        Return ancestors grouped by tier distance from source_skill_id.

        Result: [[L-1 parents], [L-2 grandparents], ...]
        Cycle-safe; stops early when no more ancestors exist.
        """
        ancestors_by_level: List[List[str]] = []
        current_frontier = [source_skill_id]
        visited: Set[str] = {source_skill_id}

        for _ in range(max_levels):
            next_frontier: List[str] = []
            for skill_id in current_frontier:
                info = self.unlock_service.hierarchy.get(skill_id)
                if not info:
                    continue
                for pid in info.get("parent_skill_ids", []):
                    if pid not in visited:
                        visited.add(pid)
                        next_frontier.append(pid)

            if not next_frontier:
                break

            ancestors_by_level.append(next_frontier)
            current_frontier = next_frontier

        return ancestors_by_level

    # ------------------------------------------------------------------
    # Apply to DB
    # ------------------------------------------------------------------

    def apply_xp_distribution(
        self,
        user_id: str,
        distribution: Dict[str, int],
    ) -> Dict[str, Dict]:
        """
        Write the calculated XP distribution to Skill records.

        Creates missing Skill rows on demand.  Recalculates level and rank
        after each XP update.  Triggers child unlock checks when a skill
        crosses the Lv20 (Rank D) threshold.

        Returns:
            {source_skill_id: {old_xp, new_xp, old_level, new_level, xp_gained}}
        """
        results: Dict[str, Dict] = {}

        for source_skill_id, xp_amount in distribution.items():
            if xp_amount <= 0:
                continue

            skill = self._get_or_create_skill(user_id, source_skill_id)
            if skill is None:
                continue

            old_xp = skill.xp
            old_level = skill.level

            skill.xp += xp_amount
            new_level = calculate_level_from_xp(skill.xp)
            skill.level = new_level
            skill.rank = get_rank_from_level(new_level).value
            skill.last_activity_at = datetime.now(timezone.utc)

            results[source_skill_id] = {
                "old_xp": old_xp,
                "new_xp": skill.xp,
                "old_level": old_level,
                "new_level": new_level,
                "xp_gained": xp_amount,
            }

            # Rule 4 gate: reaching Lv20 unlocks children
            if old_level < _UNLOCK_LEVEL <= new_level:
                self._check_children_unlocks(user_id, source_skill_id)

        self.db.commit()
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_skill(
        self, user_id: str, source_skill_id: str
    ) -> Optional[Skill]:
        """
        Return the Skill row for this user + source_skill_id, creating it if
        absent.  Returns None if the source_skill_id is not in the global KB.
        """
        global_id = self.unlock_service._resolve_global_id(source_skill_id)
        if global_id is None:
            return None

        skill = (
            self.db.query(Skill)
            .filter(Skill.user_id == user_id, Skill.global_skill_id == global_id)
            .first()
        )
        if skill is not None:
            return skill

        # Create a new Skill row
        skill_info = self.unlock_service.hierarchy.get(source_skill_id)
        canonical = (
            skill_info["canonical_name"]
            if skill_info
            else source_skill_id
        )
        skill = Skill(
            user_id=user_id,
            global_skill_id=global_id,
            name=canonical,
            canonical_name=canonical.lower().replace(" ", "_"),
            xp=0,
            level=1,
            rank=get_rank_from_level(1).value,
        )
        self.db.add(skill)
        self.db.flush()  # Populate PK without committing
        return skill

    def _check_children_unlocks(
        self, user_id: str, parent_source_skill_id: str
    ) -> None:
        """
        After a parent crosses Lv20, evaluate every direct child in the
        hierarchy and persist any pending state transitions.
        """
        for skill_id, skill_info in self.unlock_service.hierarchy.items():
            if parent_source_skill_id not in skill_info.get("parent_skill_ids", []):
                continue

            state = self.unlock_service.get_or_create_skill_state(user_id, skill_id)
            if state is None:
                continue

            target = self.unlock_service.evaluate_unlock_state(user_id, skill_id)
            if state.state != target:
                self.unlock_service.transition_state(
                    user_id,
                    skill_id,
                    target,
                    unlock_parent_skill_id=parent_source_skill_id,
                )
