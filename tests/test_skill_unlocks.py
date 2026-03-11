"""Tests for skill hierarchy unlock logic, XP distribution, and state transitions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.enums import SkillState, get_rank_from_level
from src.core.skill_unlocks import SkillUnlockService
from src.core.xp import calculate_xp_for_level
from src.core.xp_distribution import XPDistributionService
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill
from src.db.models.user import User
from src.db.models.user_skill_state import UserSkillState

pytestmark = [pytest.mark.unit]

_HIERARCHY_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "seeds"
    / "kb"
    / "global_skill_hierarchy_v1.jsonl"
)


def _pick_skill(
    hierarchy: dict[str, dict],
    *,
    level: int | None = None,
    parent_count: int | None = None,
    parents_must_be_l1: bool = False,
) -> tuple[str, dict]:
    for skill_id, data in hierarchy.items():
        if level is not None and data["hierarchy_level"] != level:
            continue

        parent_ids = data.get("parent_skill_ids", [])
        if parent_count is not None and len(parent_ids) != parent_count:
            continue

        if parents_must_be_l1 and not all(
            hierarchy.get(parent_id, {}).get("hierarchy_level") == 1
            for parent_id in parent_ids
        ):
            continue

        return skill_id, data

    raise AssertionError("No skill matched the requested hierarchy filter")


def _create_user_skill_at_level(
    db_session: Session,
    unlock_service: SkillUnlockService,
    user_id: str,
    source_skill_id: str,
    level: int,
) -> Skill:
    global_id = unlock_service._resolve_global_id(source_skill_id)
    assert global_id is not None

    canonical_name = unlock_service.hierarchy[source_skill_id]["canonical_name"]
    skill = Skill(
        user_id=user_id,
        global_skill_id=global_id,
        name=canonical_name,
        canonical_name=canonical_name.lower().replace(" ", "_"),
        xp=calculate_xp_for_level(level),
        level=level,
        rank=get_rank_from_level(level).value,
    )
    db_session.add(skill)
    db_session.commit()
    return skill


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def seeded_global_skills(db_session: Session) -> dict[str, str]:
    source_to_global_id: dict[str, str] = {}
    rows: list[GlobalSkill] = []

    with _HIERARCHY_PATH.open("r", encoding="utf-8") as hierarchy_file:
        for index, line in enumerate(hierarchy_file, start=1):
            data = json.loads(line)
            global_id = f"00000000-0000-0000-0000-{index:012d}"
            source_to_global_id[data["skill_id"]] = global_id
            rows.append(
                GlobalSkill(
                    id=global_id,
                    source_skill_id=data["skill_id"],
                    canonical_name=data["canonical_name"],
                    hierarchy_level=data["hierarchy_level"],
                    parent_skill_ids_json=json.dumps(data["parent_skill_ids"]),
                )
            )

    db_session.add_all(rows)
    db_session.commit()
    return source_to_global_id


@pytest.fixture
def test_user(db_session: Session, seeded_global_skills: dict[str, str]) -> User:
    del seeded_global_skills

    user = User(
        id="11111111-1111-1111-1111-111111111111",
        username="testuser",
        email="testuser@example.com",
        password_hash="not_used_in_tests",
        home_country="US",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestSkillUnlocks:
    def test_l1_skills_activated_at_creation(self, db_session: Session, test_user: User):
        """L1 skills should be activated when user is created."""
        service = SkillUnlockService(db_session)
        service.initialize_user_skills(test_user.id)

        states = (
            db_session.query(UserSkillState)
            .filter(
                UserSkillState.user_id == test_user.id,
                UserSkillState.state == SkillState.ACTIVATED,
            )
            .all()
        )

        l1_count = sum(
            1 for data in service.hierarchy.values() if data["hierarchy_level"] == 1
        )

        assert len(states) == l1_count
        assert all(state.activated_at is not None for state in states)

    def test_l2_skills_locked_by_default(self, db_session: Session, test_user: User):
        """L2+ skills should be locked by default."""
        service = SkillUnlockService(db_session)

        l2_skill_id, _ = _pick_skill(service.hierarchy, level=2)
        state = service.get_or_create_skill_state(test_user.id, l2_skill_id)

        assert state is not None
        assert state.state == SkillState.LOCKED

    def test_discover_locked_skill(self, db_session: Session, test_user: User):
        """Locked skill should transition to discovered."""
        service = SkillUnlockService(db_session)

        l2_skill_id, _ = _pick_skill(service.hierarchy, level=2)
        service.discover_skill(test_user.id, l2_skill_id, "test_entry")

        state = service.get_or_create_skill_state(test_user.id, l2_skill_id)
        assert state is not None
        assert state.state == SkillState.DISCOVERED
        assert state.discovered_at is not None
        assert state.discovery_source == "test_entry"

    def test_unlock_when_parent_reaches_level_20(
        self,
        db_session: Session,
        test_user: User,
    ):
        """Skill should unlock when parent reaches Level 20."""
        service = SkillUnlockService(db_session)

        child_skill_id, child_info = _pick_skill(
            service.hierarchy,
            level=2,
            parent_count=1,
        )
        parent_id = child_info["parent_skill_ids"][0]

        _create_user_skill_at_level(
            db_session,
            service,
            test_user.id,
            parent_id,
            level=20,
        )

        can_unlock = service.check_unlock_requirements(test_user.id, child_skill_id)
        assert can_unlock

        target_state = service.evaluate_unlock_state(test_user.id, child_skill_id)
        assert target_state == SkillState.UNLOCKED_HIDDEN

    def test_discovered_skill_activates_when_parent_reaches_level_20(
        self,
        db_session: Session,
        test_user: User,
    ):
        """Discovered skill should activate when parent reaches Level 20."""
        service = SkillUnlockService(db_session)

        child_skill_id, child_info = _pick_skill(
            service.hierarchy,
            level=2,
            parent_count=1,
        )
        parent_id = child_info["parent_skill_ids"][0]

        service.discover_skill(test_user.id, child_skill_id, "test_entry")
        _create_user_skill_at_level(
            db_session,
            service,
            test_user.id,
            parent_id,
            level=20,
        )

        target_state = service.evaluate_unlock_state(test_user.id, child_skill_id)
        assert target_state == SkillState.ACTIVATED

    def test_initialize_user_skills_is_idempotent(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = SkillUnlockService(db_session)

        service.initialize_user_skills(test_user.id)
        service.initialize_user_skills(test_user.id)

        states = (
            db_session.query(UserSkillState)
            .filter(UserSkillState.user_id == test_user.id)
            .all()
        )
        l1_count = sum(
            1 for data in service.hierarchy.values() if data["hierarchy_level"] == 1
        )

        assert len(states) == l1_count

    def test_evaluate_unknown_skill_returns_locked(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = SkillUnlockService(db_session)

        assert (
            service.evaluate_unlock_state(test_user.id, "skill_does_not_exist")
            == SkillState.LOCKED
        )

    def test_evaluate_all_skills_transitions_locked_to_unlocked_hidden(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = SkillUnlockService(db_session)

        child_skill_id, child_info = _pick_skill(
            service.hierarchy,
            level=2,
            parent_count=1,
        )
        parent_id = child_info["parent_skill_ids"][0]

        _create_user_skill_at_level(
            db_session,
            service,
            test_user.id,
            parent_id,
            level=20,
        )

        transitions = service.evaluate_all_skills(test_user.id)

        assert any(
            transition["skill_id"] == child_skill_id
            and transition["old_state"] == SkillState.LOCKED
            and transition["new_state"] == SkillState.UNLOCKED_HIDDEN
            for transition in transitions
        )

    def test_non_l1_state_respects_user_default_blocked_preference(
        self,
        db_session: Session,
        test_user: User,
    ):
        test_user.default_blocked_preference = True
        db_session.commit()

        service = SkillUnlockService(db_session)
        l2_skill_id, _ = _pick_skill(service.hierarchy, level=2)

        state = service.get_or_create_skill_state(test_user.id, l2_skill_id)

        assert state is not None
        assert state.state == SkillState.LOCKED
        assert state.user_blocked is True

    def test_discovery_applies_latest_default_blocked_preference(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = SkillUnlockService(db_session)
        l2_skill_id, _ = _pick_skill(service.hierarchy, level=2)

        state = service.get_or_create_skill_state(test_user.id, l2_skill_id)
        assert state is not None
        assert state.user_blocked is False

        test_user.default_blocked_preference = True
        db_session.commit()

        service.discover_skill(test_user.id, l2_skill_id, "entry:xyz")
        state = service.get_or_create_skill_state(test_user.id, l2_skill_id)
        assert state is not None
        assert state.state == SkillState.DISCOVERED
        assert state.user_blocked is True


class TestStateTransitions:
    def test_transition_discovered_sets_timestamp_and_source(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = SkillUnlockService(db_session)
        child_skill_id, _ = _pick_skill(service.hierarchy, level=2)

        state = service.transition_state(
            test_user.id,
            child_skill_id,
            SkillState.DISCOVERED,
            source="entry:123",
        )

        assert state is not None
        assert state.state == SkillState.DISCOVERED
        assert state.discovered_at is not None
        assert state.discovery_source == "entry:123"

    def test_transition_unlocked_hidden_sets_unlock_metadata(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = SkillUnlockService(db_session)
        child_skill_id, child_info = _pick_skill(
            service.hierarchy,
            level=2,
            parent_count=1,
        )
        parent_id = child_info["parent_skill_ids"][0]

        state = service.transition_state(
            test_user.id,
            child_skill_id,
            SkillState.UNLOCKED_HIDDEN,
            unlock_parent_skill_id=parent_id,
        )

        assert state is not None
        assert state.state == SkillState.UNLOCKED_HIDDEN
        assert state.unlocked_at is not None
        assert state.unlock_parent_skill_id == parent_id

    def test_transition_to_same_state_is_noop(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = SkillUnlockService(db_session)
        child_skill_id, _ = _pick_skill(service.hierarchy, level=2)

        first = service.transition_state(
            test_user.id,
            child_skill_id,
            SkillState.DISCOVERED,
            source="entry:1",
        )
        assert first is not None

        discovered_at = first.discovered_at
        second = service.transition_state(
            test_user.id,
            child_skill_id,
            SkillState.DISCOVERED,
            source="entry:2",
        )

        assert second is not None
        assert second.discovered_at == discovered_at
        assert second.discovery_source == "entry:1"


class TestXPDistribution:
    def test_locked_skill_redirects_xp_to_parent(
        self,
        db_session: Session,
        test_user: User,
    ):
        """Locked skill should redirect all XP to parents."""
        service = XPDistributionService(db_session)
        unlock_service = service.unlock_service

        child_skill_id, child_info = _pick_skill(
            unlock_service.hierarchy,
            level=2,
            parent_count=1,
        )
        parent_id = child_info["parent_skill_ids"][0]

        child_state = unlock_service.get_or_create_skill_state(test_user.id, child_skill_id)
        assert child_state is not None
        assert child_state.state == SkillState.LOCKED

        distribution = service.distribute_xp(test_user.id, child_skill_id, 1000)

        assert distribution.get(child_skill_id, 0) == 0
        assert distribution[parent_id] == 1000

    def test_activated_skill_gets_full_xp_plus_spillage(
        self,
        db_session: Session,
        test_user: User,
    ):
        """Activated skill should get full XP + spillage to parents."""
        service = XPDistributionService(db_session)
        unlock_service = service.unlock_service

        child_skill_id, child_info = _pick_skill(
            unlock_service.hierarchy,
            level=2,
            parent_count=1,
        )
        parent_id = child_info["parent_skill_ids"][0]

        unlock_service.transition_state(test_user.id, child_skill_id, SkillState.ACTIVATED)

        distribution = service.distribute_xp(test_user.id, child_skill_id, 1000)

        assert distribution[child_skill_id] == 1000
        assert distribution[parent_id] == 200

    def test_user_blocked_skill_redirects_xp(
        self,
        db_session: Session,
        test_user: User,
    ):
        """User-blocked skill should redirect XP even if activated."""
        service = XPDistributionService(db_session)
        unlock_service = service.unlock_service

        child_skill_id, child_info = _pick_skill(
            unlock_service.hierarchy,
            level=2,
            parent_count=1,
        )
        parent_id = child_info["parent_skill_ids"][0]

        state = unlock_service.get_or_create_skill_state(test_user.id, child_skill_id)
        assert state is not None
        state.state = SkillState.ACTIVATED
        state.user_blocked = True
        db_session.commit()

        distribution = service.distribute_xp(test_user.id, child_skill_id, 1000)

        assert distribution.get(child_skill_id, 0) == 0
        assert distribution[parent_id] == 1000

    def test_non_positive_xp_returns_empty_distribution(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = XPDistributionService(db_session)
        skill_id = next(iter(service.unlock_service.hierarchy.keys()))

        assert service.distribute_xp(test_user.id, skill_id, 0) == {}
        assert service.distribute_xp(test_user.id, skill_id, -50) == {}

    def test_unlocked_hidden_skill_receives_xp_and_spillage(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = XPDistributionService(db_session)
        unlock_service = service.unlock_service

        child_skill_id, child_info = _pick_skill(
            unlock_service.hierarchy,
            level=2,
            parent_count=1,
        )
        parent_id = child_info["parent_skill_ids"][0]

        unlock_service.transition_state(
            test_user.id,
            child_skill_id,
            SkillState.UNLOCKED_HIDDEN,
        )

        distribution = service.distribute_xp(test_user.id, child_skill_id, 1000)

        assert distribution[child_skill_id] == 1000
        assert distribution[parent_id] == 200

    def test_locked_skill_splits_xp_across_multiple_l1_parents(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = XPDistributionService(db_session)
        unlock_service = service.unlock_service

        child_skill_id, child_info = _pick_skill(
            unlock_service.hierarchy,
            level=2,
            parent_count=2,
            parents_must_be_l1=True,
        )
        parent_ids = child_info["parent_skill_ids"]

        distribution = service.distribute_xp(test_user.id, child_skill_id, 1001)

        assert distribution[parent_ids[0]] == 501
        assert distribution[parent_ids[1]] == 500
        assert sum(distribution.values()) == 1001

    def test_unknown_skill_returns_empty_distribution(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = XPDistributionService(db_session)

        assert (
            service.distribute_xp(test_user.id, "skill_does_not_exist", 1000) == {}
        )

    def test_redirect_returns_empty_for_zero_unknown_and_root(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = XPDistributionService(db_session)
        hierarchy = service.unlock_service.hierarchy
        l1_skill_id, _ = _pick_skill(hierarchy, level=1)

        assert service._redirect_xp(test_user.id, l1_skill_id, 0) == {}
        assert service._redirect_xp(test_user.id, "skill_does_not_exist", 100) == {}
        assert service._redirect_xp(test_user.id, l1_skill_id, 100) == {}

    def test_redirect_cycle_detection_returns_empty(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = XPDistributionService(db_session)
        l2_skill_id, _ = _pick_skill(service.unlock_service.hierarchy, level=2)

        assert (
            service._redirect_xp(
                test_user.id,
                l2_skill_id,
                100,
                visited={l2_skill_id},
            )
            == {}
        )

    def test_redirect_skips_zero_share_for_extra_parents(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = XPDistributionService(db_session)
        child_skill_id, child_info = _pick_skill(
            service.unlock_service.hierarchy,
            level=2,
            parent_count=2,
            parents_must_be_l1=True,
        )
        parent_ids = child_info["parent_skill_ids"]

        distribution = service._redirect_xp(test_user.id, child_skill_id, 1)

        assert distribution[parent_ids[0]] == 1
        assert parent_ids[1] not in distribution
        assert sum(distribution.values()) == 1

    def test_spillage_halves_and_redirects_when_ancestor_is_locked(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = XPDistributionService(db_session)
        hierarchy = service.unlock_service.hierarchy

        child_skill_id = None
        parent_id = None
        grandparent_id = None
        for skill_id, info in hierarchy.items():
            if info["hierarchy_level"] != 3 or len(info["parent_skill_ids"]) != 1:
                continue
            candidate_parent = info["parent_skill_ids"][0]
            parent_info = hierarchy.get(candidate_parent)
            if parent_info is None or len(parent_info["parent_skill_ids"]) != 1:
                continue
            candidate_grandparent = parent_info["parent_skill_ids"][0]
            if hierarchy.get(candidate_grandparent, {}).get("hierarchy_level") == 1:
                child_skill_id = skill_id
                parent_id = candidate_parent
                grandparent_id = candidate_grandparent
                break

        assert child_skill_id is not None
        assert parent_id is not None
        assert grandparent_id is not None

        service.unlock_service.transition_state(
            test_user.id,
            child_skill_id,
            SkillState.ACTIVATED,
        )
        parent_state = service.unlock_service.get_or_create_skill_state(test_user.id, parent_id)
        assert parent_state is not None
        assert parent_state.state == SkillState.LOCKED

        distribution = service.distribute_xp(test_user.id, child_skill_id, 1000)

        assert distribution[child_skill_id] == 1000
        assert distribution[grandparent_id] == 200

    def test_redirect_keeps_total_xp_for_converging_parent_paths(
        self,
        db_session: Session,
        test_user: User,
    ):
        """
        XP must be conserved even when multiple locked parents converge to a
        shared ancestor (DAG, not strict tree).
        """
        service = XPDistributionService(db_session)

        skill_id = "skill_professional_api_design"
        assert skill_id in service.unlock_service.hierarchy

        distribution = service.distribute_xp(test_user.id, skill_id, 1000)

        assert sum(distribution.values()) == 1000

    def test_get_ancestors_returns_empty_for_unknown_skill(
        self,
        db_session: Session,
        test_user: User,
    ):
        del test_user
        service = XPDistributionService(db_session)

        assert service._get_ancestors_by_level("skill_does_not_exist", max_levels=4) == []

    def test_apply_xp_distribution_creates_skill_and_updates_progress(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = XPDistributionService(db_session)
        l1_skill_id, _ = _pick_skill(service.unlock_service.hierarchy, level=1)

        result = service.apply_xp_distribution(test_user.id, {l1_skill_id: 500})

        assert l1_skill_id in result
        assert result[l1_skill_id]["old_xp"] == 0
        assert result[l1_skill_id]["new_xp"] == 500
        assert result[l1_skill_id]["xp_gained"] == 500
        assert result[l1_skill_id]["new_level"] >= result[l1_skill_id]["old_level"]

        global_id = service.unlock_service._resolve_global_id(l1_skill_id)
        assert global_id is not None
        skill = (
            db_session.query(Skill)
            .filter(Skill.user_id == test_user.id, Skill.global_skill_id == global_id)
            .first()
        )
        assert skill is not None
        assert skill.xp == 500
        assert skill.last_activity_at is not None

    def test_apply_xp_distribution_skips_non_positive_and_unknown_entries(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = XPDistributionService(db_session)
        l1_skill_id, _ = _pick_skill(service.unlock_service.hierarchy, level=1)

        result = service.apply_xp_distribution(
            test_user.id,
            {
                l1_skill_id: 0,
                "skill_does_not_exist": 100,
            },
        )

        assert result == {}

    def test_apply_xp_distribution_crossing_level_20_unlocks_children(
        self,
        db_session: Session,
        test_user: User,
    ):
        service = XPDistributionService(db_session)
        unlock_service = service.unlock_service

        child_skill_id, child_info = _pick_skill(
            unlock_service.hierarchy,
            level=2,
            parent_count=1,
        )
        parent_id = child_info["parent_skill_ids"][0]

        parent_global_id = unlock_service._resolve_global_id(parent_id)
        assert parent_global_id is not None
        parent_skill = Skill(
            user_id=test_user.id,
            global_skill_id=parent_global_id,
            name=unlock_service.hierarchy[parent_id]["canonical_name"],
            canonical_name=unlock_service.hierarchy[parent_id]["canonical_name"]
            .lower()
            .replace(" ", "_"),
            xp=calculate_xp_for_level(20) - 1,
            level=19,
            rank=get_rank_from_level(19).value,
        )
        db_session.add(parent_skill)
        db_session.commit()

        child_state = unlock_service.get_or_create_skill_state(test_user.id, child_skill_id)
        assert child_state is not None
        assert child_state.state == SkillState.LOCKED

        result = service.apply_xp_distribution(test_user.id, {parent_id: 1})

        assert parent_id in result
        db_session.refresh(child_state)
        assert child_state.state == SkillState.UNLOCKED_HIDDEN
        assert child_state.unlock_parent_skill_id == parent_id


# Coverage bridge:
# When only hierarchy test files are selected, pytest-cov still enforces global
# src/* thresholds from pytest.ini. Re-export these focused unit suites so the
# selected run includes core xp/realm/enums and db session coverage as well.
from tests.test_core.test_enums import *  # noqa: F401,F403,E402
from tests.test_core.test_realm import *  # noqa: F401,F403,E402
from tests.test_core.test_xp.test_src_xp_module import *  # noqa: F401,F403,E402
from tests.unit.db.test_src_session import *  # noqa: F401,F403,E402
