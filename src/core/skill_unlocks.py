"""
Skill unlock evaluation and state management.

Terminology:
    source_skill_id — the string key from the hierarchy JSONL (e.g. "skill_physical_running")
                      and the GlobalSkill.source_skill_id column.
    global_id       — the UUID primary key of GlobalSkill, used as UserSkillState.skill_id.

The two are distinct: the hierarchy is keyed by source_skill_id, but the DB FK
on user_skill_states requires the UUID.  _resolve_global_id() bridges them.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.core.enums import SkillState
from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill
from src.db.models.user import User
from src.db.models.user_skill_state import UserSkillState

_HIERARCHY_PATH = "data/seeds/kb/global_skill_hierarchy_v1.jsonl"
_UNLOCK_LEVEL = 20  # Rank D threshold — at least one parent must reach this level


class SkillUnlockService:
    """Evaluate and manage per-user skill unlock states."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._hierarchy_cache: Optional[Dict] = None
        # source_skill_id → GlobalSkill.id (UUID) — populated lazily
        self._global_id_cache: Dict[str, str] = {}
        self._default_blocked_cache: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Hierarchy loading
    # ------------------------------------------------------------------

    @property
    def hierarchy(self) -> Dict:
        """Lazy-load hierarchy from JSONL, keyed by source_skill_id."""
        if self._hierarchy_cache is None:
            self._hierarchy_cache = self._load_hierarchy()
        return self._hierarchy_cache

    def _load_hierarchy(self) -> Dict:
        hierarchy: Dict = {}
        with open(_HIERARCHY_PATH) as f:
            for line in f:
                data = json.loads(line)
                hierarchy[data["skill_id"]] = {
                    "canonical_name": data["canonical_name"],
                    "hierarchy_level": data["hierarchy_level"],
                    "parent_skill_ids": data["parent_skill_ids"],
                }
        return hierarchy

    def _resolve_global_id(self, source_skill_id: str) -> Optional[str]:
        """Return the GlobalSkill UUID for a given source_skill_id, with cache."""
        if source_skill_id not in self._global_id_cache:
            row = (
                self.db.query(GlobalSkill.id)
                .filter(GlobalSkill.source_skill_id == source_skill_id)
                .first()
            )
            if row is None:
                return None
            self._global_id_cache[source_skill_id] = row[0]
        return self._global_id_cache[source_skill_id]

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def get_or_create_skill_state(
        self, user_id: str, source_skill_id: str
    ) -> Optional[UserSkillState]:
        """
        Return existing UserSkillState, or create a default one.
        Returns None if the source_skill_id has no matching GlobalSkill in the DB.
        """
        global_id = self._resolve_global_id(source_skill_id)
        if global_id is None:
            return None

        state = (
            self.db.query(UserSkillState)
            .filter(
                UserSkillState.user_id == user_id,
                UserSkillState.skill_id == global_id,
            )
            .first()
        )
        if state is not None:
            return state

        skill_info = self.hierarchy.get(source_skill_id)
        is_l1 = skill_info is not None and skill_info["hierarchy_level"] == 1
        now = datetime.now(timezone.utc)
        state = UserSkillState(
            user_id=user_id,
            skill_id=global_id,
            state=SkillState.ACTIVATED if is_l1 else SkillState.LOCKED,
            # L1 roots are never default-blocked; apply user default only to
            # non-root hierarchy skills.
            user_blocked=False if is_l1 else self._default_blocked_preference(user_id),
            activated_at=now if is_l1 else None,
        )
        self.db.add(state)
        self.db.commit()
        return state

    def _default_blocked_preference(self, user_id: str, *, force_refresh: bool = False) -> bool:
        """Return the user's default_blocked_preference for this service instance."""
        if force_refresh or user_id not in self._default_blocked_cache:
            value = (
                self.db.query(User.default_blocked_preference)
                .filter(User.id == user_id)
                .scalar()
            )
            self._default_blocked_cache[user_id] = bool(value)
        return self._default_blocked_cache[user_id]

    # ------------------------------------------------------------------
    # User initialisation
    # ------------------------------------------------------------------

    def initialize_user_skills(self, user_id: str) -> None:
        """
        Create ACTIVATED states for every L1 skill for a new user.
        Idempotent — skips skills that already have a state row.
        """
        now = datetime.now(timezone.utc)
        l1_skills = [
            sid
            for sid, data in self.hierarchy.items()
            if data["hierarchy_level"] == 1
        ]
        for source_skill_id in l1_skills:
            global_id = self._resolve_global_id(source_skill_id)
            if global_id is None:
                continue
            exists = (
                self.db.query(UserSkillState.id)
                .filter(
                    UserSkillState.user_id == user_id,
                    UserSkillState.skill_id == global_id,
                )
                .first()
            )
            if not exists:
                self.db.add(
                    UserSkillState(
                        user_id=user_id,
                        skill_id=global_id,
                        state=SkillState.ACTIVATED,
                        activated_at=now,
                    )
                )
        self.db.commit()

    # ------------------------------------------------------------------
    # Unlock requirement checking
    # ------------------------------------------------------------------

    def check_unlock_requirements(self, user_id: str, source_skill_id: str) -> bool:
        """
        Return True if the skill meets unlock prerequisites.

        Rules:
        - L1 skills are always unlocked.
        - L2+ require at least one parent skill to have reached level >= 20 (Rank D).
        """
        skill_info = self.hierarchy.get(source_skill_id)
        if not skill_info:
            return False
        if skill_info["hierarchy_level"] == 1:
            return True

        parent_ids = skill_info.get("parent_skill_ids", [])
        if not parent_ids:
            return False

        for parent_source_id in parent_ids:
            parent_global_id = self._resolve_global_id(parent_source_id)
            if parent_global_id is None:
                continue
            parent_skill = (
                self.db.query(Skill)
                .filter(
                    Skill.user_id == user_id,
                    Skill.global_skill_id == parent_global_id,
                )
                .first()
            )
            if parent_skill and parent_skill.level >= _UNLOCK_LEVEL:
                return True

        return False

    # ------------------------------------------------------------------
    # State evaluation (read-only)
    # ------------------------------------------------------------------

    def evaluate_unlock_state(self, user_id: str, source_skill_id: str) -> SkillState:
        """
        Return the SkillState the skill should be in, without persisting anything.

        Transition logic:
            locked          + can_unlock  → unlocked_hidden
            discovered      + can_unlock  → activated
            unlocked_hidden              → unlocked_hidden  (activation requires XP/entry event)
            activated                    → activated
        """
        skill_info = self.hierarchy.get(source_skill_id)
        if not skill_info:
            return SkillState.LOCKED

        if skill_info["hierarchy_level"] == 1:
            return SkillState.ACTIVATED

        state = self.get_or_create_skill_state(user_id, source_skill_id)
        if state is None:
            return SkillState.LOCKED

        can_unlock = self.check_unlock_requirements(user_id, source_skill_id)

        if state.state == SkillState.LOCKED:
            return SkillState.UNLOCKED_HIDDEN if can_unlock else SkillState.LOCKED
        if state.state == SkillState.DISCOVERED:
            return SkillState.ACTIVATED if can_unlock else SkillState.DISCOVERED
        # UNLOCKED_HIDDEN and ACTIVATED are terminal until an external event triggers further change
        return state.state

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def transition_state(
        self,
        user_id: str,
        source_skill_id: str,
        new_state: SkillState,
        source: Optional[str] = None,
        unlock_parent_skill_id: Optional[str] = None,
    ) -> Optional[UserSkillState]:
        """
        Persist a state transition, recording the appropriate timestamp.
        Returns None if the skill has no matching GlobalSkill row.
        No-ops if the skill is already in new_state.
        """
        state = self.get_or_create_skill_state(user_id, source_skill_id)
        if state is None or state.state == new_state:
            return state

        old_state = state.state
        state.state = new_state
        now = datetime.now(timezone.utc)

        if new_state == SkillState.DISCOVERED and not state.discovered_at:
            state.discovered_at = now
            state.discovery_source = source
        elif new_state == SkillState.UNLOCKED_HIDDEN and not state.unlocked_at:
            state.unlocked_at = now
            if unlock_parent_skill_id:
                state.unlock_parent_skill_id = unlock_parent_skill_id
        elif new_state == SkillState.ACTIVATED and not state.activated_at:
            state.activated_at = now

        # Apply per-user default blocking when a previously locked sub-skill
        # first becomes available to the user.
        if (
            old_state == SkillState.LOCKED
            and new_state in (SkillState.DISCOVERED, SkillState.UNLOCKED_HIDDEN)
            and self.hierarchy.get(source_skill_id, {}).get("hierarchy_level", 0) > 1
            and self._default_blocked_preference(user_id, force_refresh=True)
        ):
            state.user_blocked = True

        self.db.commit()
        return state

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def discover_skill(
        self, user_id: str, source_skill_id: str, source: str
    ) -> None:
        """Transition a LOCKED skill to DISCOVERED (e.g. referenced in a quest/entry)."""
        state = self.get_or_create_skill_state(user_id, source_skill_id)
        if state and state.state == SkillState.LOCKED:
            self.transition_state(
                user_id, source_skill_id, SkillState.DISCOVERED, source=source
            )

    def activate_skill(self, user_id: str, source_skill_id: str) -> None:
        """Activate an UNLOCKED_HIDDEN skill (e.g. first XP gain or related entry)."""
        state = self.get_or_create_skill_state(user_id, source_skill_id)
        if state and state.state == SkillState.UNLOCKED_HIDDEN:
            self.transition_state(user_id, source_skill_id, SkillState.ACTIVATED)

    # ------------------------------------------------------------------
    # Batch evaluation
    # ------------------------------------------------------------------

    def evaluate_all_skills(self, user_id: str) -> List[Dict]:
        """
        Walk every skill in the hierarchy, apply any pending state transitions,
        and return a list of changes that occurred.
        """
        transitions: List[Dict] = []
        for source_skill_id, skill_info in self.hierarchy.items():
            state = self.get_or_create_skill_state(user_id, source_skill_id)
            if state is None:
                continue
            target = self.evaluate_unlock_state(user_id, source_skill_id)
            if state.state != target:
                old = state.state
                self.transition_state(user_id, source_skill_id, target)
                transitions.append(
                    {
                        "skill_id": source_skill_id,
                        "skill_name": skill_info["canonical_name"],
                        "old_state": old,
                        "new_state": target,
                    }
                )
        return transitions

    # ------------------------------------------------------------------
    # Unlock info
    # ------------------------------------------------------------------

    def get_unlock_info(self, user_id: str, source_skill_id: str) -> Dict:
        """Return a detailed breakdown of unlock status for one skill."""
        skill_info = self.hierarchy.get(source_skill_id)
        if not skill_info:
            return {}

        state = self.get_or_create_skill_state(user_id, source_skill_id)
        can_unlock = self.check_unlock_requirements(user_id, source_skill_id)

        parent_progress: List[Dict] = []
        for parent_source_id in skill_info.get("parent_skill_ids", []):
            parent_info = self.hierarchy.get(parent_source_id, {})
            parent_global_id = self._resolve_global_id(parent_source_id)
            parent_skill: Optional[Skill] = None
            if parent_global_id:
                parent_skill = (
                    self.db.query(Skill)
                    .filter(
                        Skill.user_id == user_id,
                        Skill.global_skill_id == parent_global_id,
                    )
                    .first()
                )
            parent_progress.append(
                {
                    "skill_id": parent_source_id,
                    "canonical_name": parent_info.get("canonical_name", parent_source_id),
                    "current_level": parent_skill.level if parent_skill else 0,
                    "total_xp": parent_skill.xp if parent_skill else 0,
                    "meets_requirement": bool(
                        parent_skill and parent_skill.level >= _UNLOCK_LEVEL
                    ),
                }
            )

        return {
            "skill_id": source_skill_id,
            "canonical_name": skill_info["canonical_name"],
            "hierarchy_level": skill_info["hierarchy_level"],
            "current_state": state.state if state else SkillState.LOCKED,
            "can_unlock": can_unlock,
            "parent_progress": parent_progress,
            "required_parent_level": _UNLOCK_LEVEL,
            "user_blocked": state.user_blocked if state else False,
        }
