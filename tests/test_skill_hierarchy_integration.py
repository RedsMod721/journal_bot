"""Integration tests for full skill hierarchy progression."""

from __future__ import annotations

import pytest

from src.core.enums import SkillState
from src.core.skill_unlocks import SkillUnlockService
from src.core.xp_distribution import XPDistributionService
from src.db.models.skill import Skill

from tests.test_skill_unlocks import (  # noqa: F401
    _create_user_skill_at_level,
    _pick_skill,
    db_session,
    seeded_global_skills,
    test_user,
)

pytestmark = [pytest.mark.integration]


class TestSkillHierarchyIntegration:
    def test_full_progression_flow(self, db_session, test_user):
        """Test complete progression: locked -> discovered -> unlocked -> activated."""
        unlock_service = SkillUnlockService(db_session)
        xp_service = XPDistributionService(db_session)

        child_skill_id, child_info = _pick_skill(
            unlock_service.hierarchy,
            level=2,
            parent_count=1,
        )
        parent_id = child_info["parent_skill_ids"][0]

        child_state = unlock_service.get_or_create_skill_state(test_user.id, child_skill_id)
        assert child_state is not None
        assert child_state.state == SkillState.LOCKED

        unlock_service.discover_skill(test_user.id, child_skill_id, "entry_123")
        child_state = unlock_service.get_or_create_skill_state(test_user.id, child_skill_id)
        assert child_state is not None
        assert child_state.state == SkillState.DISCOVERED

        _create_user_skill_at_level(
            db_session,
            unlock_service,
            test_user.id,
            parent_id,
            level=20,
        )

        transitions = unlock_service.evaluate_all_skills(test_user.id)
        assert any(
            transition["skill_id"] == child_skill_id
            and transition["old_state"] == SkillState.DISCOVERED
            and transition["new_state"] == SkillState.ACTIVATED
            for transition in transitions
        )

        child_state = unlock_service.get_or_create_skill_state(test_user.id, child_skill_id)
        assert child_state is not None
        assert child_state.state == SkillState.ACTIVATED

        distribution = xp_service.distribute_xp(test_user.id, child_skill_id, 1000)

        assert distribution[child_skill_id] == 1000
        assert distribution[parent_id] == 200

        parent_global_id = unlock_service._resolve_global_id(parent_id)
        assert parent_global_id is not None
        parent_skill = (
            db_session.query(Skill)
            .filter(Skill.user_id == test_user.id, Skill.global_skill_id == parent_global_id)
            .first()
        )
        assert parent_skill is not None
        assert parent_skill.level == 20
