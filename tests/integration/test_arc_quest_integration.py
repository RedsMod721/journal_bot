"""
Arc-Quest integration tests.

Tests story arcs affecting quest XP rewards (Section 10.6.2 — T3 multiplier).

Arc multiplier chain:
    T1 = floor(base_xp * troll_bp / 10000)
    T2 = floor(T1  * variety_bp / 10000)
    T3 = floor(T2  * arc_bp    / 10000)   ← arc reward multiplier
    final_xp = max(0, T3 - penalty)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401 — ensures all tables are registered
from src.ai.pipeline_steps.quest_matcher_step import QuestMatcherStep
from src.core.arc_lifecycle import ArcLifecycleService
from src.db.base import Base
from src.db.models.journal_entry import JournalEntry
from src.db.models.skill import Skill
from src.db.models.user import User

pytestmark = [pytest.mark.integration]

# ── Fixed IDs so assertions are deterministic ──────────────────────────────
_USER_ID = "00000000-0000-0000-0000-000000000001"
_SKILL_ID = "00000000-0000-0000-0000-000000000002"
_ENTRY_ID = "00000000-0000-0000-0000-000000000003"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session() -> Session:  # type: ignore[misc]
    """Fresh in-memory SQLite DB with the full schema for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    LocalSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = LocalSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def test_user(db_session: Session) -> User:
    user = User(
        id=_USER_ID,
        username="arcquest_user",
        email="arcquest@example.com",
        password_hash="x",
        home_country="US",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def test_skill(db_session: Session, test_user: User) -> Skill:
    skill = Skill(
        id=_SKILL_ID,
        user_id=test_user.id,
        name="Python Programming",
        canonical_name="python_programming",
        xp=0,
        level=1,
        rank="F",
    )
    db_session.add(skill)
    db_session.commit()
    return skill


@pytest.fixture()
def test_entry(db_session: Session, test_user: User, test_skill: Skill) -> JournalEntry:
    """Completed journal entry — quest matcher requires status='completed'."""
    entry = JournalEntry(
        id=_ENTRY_ID,
        user_id=test_user.id,
        content="Coded Python for two focused hours and reviewed architecture.",
        entry_type="text",
        status="completed",
        question_state="none",
        processed_at=datetime.now(timezone.utc),
    )
    db_session.add(entry)
    db_session.commit()
    return entry


# ── Helper ─────────────────────────────────────────────────────────────────


def _run_step(
    db_session: Session,
    test_user: User,
    test_entry: JournalEntry,
    test_skill: Skill,
    *,
    troll_multiplier_bp: int = 10000,
    variety_multiplier_bp: int = 10000,
) -> dict:
    """Execute QuestMatcherStep with a single-skill structured_data payload."""
    structured_data = {
        "extraction_confidence_score": 80,  # 80.0 >> default threshold 0.65
        "skills_weights_bp": {test_skill.id: 10000},
        "pattern_hits_json": [],
    }
    step = QuestMatcherStep(db_session)
    return step.execute(
        user=test_user,
        entry=test_entry,
        structured_data=structured_data,
        troll_multiplier_bp=troll_multiplier_bp,
        variety_multiplier_bp=variety_multiplier_bp,
        processing_run_id="arc_quest_test",
    )


# ── Tests ──────────────────────────────────────────────────────────────────


class TestArcQuestXPMultiplier:
    """Story arc reward multiplier applied at T3 of the XP chain."""

    def test_no_active_arc_default_multipliers(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill: Skill
    ) -> None:
        """No active arc → 1.0× multiplier → 480 XP (baseline)."""
        result = _run_step(db_session, test_user, test_entry, test_skill)

        assert "error" not in result
        assert result["instant_quest"] is not None
        # T1=480, T2=480, T3=floor(480*10000/10000)=480
        assert result["total_xp_awarded"] == 480

    def test_redemption_arc_increases_quest_rewards(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill: Skill
    ) -> None:
        """Redemption arc with xp_reward_multiplier_bp=15000 → 1.5× → 720 XP."""
        arc_svc = ArcLifecycleService(db_session)
        arc_svc.create_arc(
            user_id=test_user.id,
            arc_type="redemption",
            xp_reward_multiplier_bp=15000,  # 1.5×
            make_active=True,
        )

        result = _run_step(db_session, test_user, test_entry, test_skill)

        assert "error" not in result
        assert result["instant_quest"] is not None
        # T1=480, T2=480, T3=floor(480*15000/10000)=720
        assert result["total_xp_awarded"] == 720

    def test_regression_arc_normal_quest_rewards(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill: Skill
    ) -> None:
        """Regression arc with default 1.0× multiplier → 480 XP (no boost)."""
        arc_svc = ArcLifecycleService(db_session)
        arc_svc.create_arc(
            user_id=test_user.id,
            arc_type="regression",
            xp_reward_multiplier_bp=10000,  # 1.0×
            make_active=True,
        )

        result = _run_step(db_session, test_user, test_entry, test_skill)

        assert "error" not in result
        assert result["instant_quest"] is not None
        # T1=480, T2=480, T3=floor(480*10000/10000)=480
        assert result["total_xp_awarded"] == 480

    def test_event_arc_custom_multiplier(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill: Skill
    ) -> None:
        """Event arc with xp_reward_multiplier_bp=12000 → 1.2× → 576 XP."""
        arc_svc = ArcLifecycleService(db_session)
        arc_svc.create_arc(
            user_id=test_user.id,
            arc_type="event",
            event_name="intense_focus_week",
            xp_reward_multiplier_bp=12000,  # 1.2×
            make_active=True,
        )

        result = _run_step(db_session, test_user, test_entry, test_skill)

        assert "error" not in result
        assert result["instant_quest"] is not None
        # T1=480, T2=480, T3=floor(480*12000/10000)=576
        assert result["total_xp_awarded"] == 576

    def test_tutorial_arc_default_multiplier(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill: Skill
    ) -> None:
        """Tutorial arc with default 1.0× multiplier → 480 XP (no boost)."""
        arc_svc = ArcLifecycleService(db_session)
        arc_svc.create_arc(
            user_id=test_user.id,
            arc_type="tutorial",
            xp_reward_multiplier_bp=10000,  # 1.0×
            make_active=True,
        )

        result = _run_step(db_session, test_user, test_entry, test_skill)

        assert "error" not in result
        assert result["instant_quest"] is not None
        assert result["total_xp_awarded"] == 480


class TestCombinedMultipliers:
    """Full T1→T2→T3 multiplier chain with arc at T3."""

    def test_combined_high_xp_redemption_plus_anomaly_plus_variety(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill: Skill
    ) -> None:
        """Max XP scenario: 2.5× anomaly × 1.25× variety × 1.5× arc = 2250 XP.

        Multiplier chain (Section 10.6.2):
            T1 = floor(480 * 25000 / 10000) = 1200
            T2 = floor(1200 * 12500 / 10000) = 1500
            T3 = floor(1500 * 15000 / 10000) = 2250
        """
        arc_svc = ArcLifecycleService(db_session)
        arc_svc.create_arc(
            user_id=test_user.id,
            arc_type="redemption",
            xp_reward_multiplier_bp=15000,  # 1.5×
            make_active=True,
        )

        result = _run_step(
            db_session,
            test_user,
            test_entry,
            test_skill,
            troll_multiplier_bp=25000,   # 2.5×
            variety_multiplier_bp=12500,  # 1.25×
        )

        assert "error" not in result
        assert result["instant_quest"] is not None
        assert result["total_xp_awarded"] == 2250

    def test_anomaly_multiplier_alone(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill: Skill
    ) -> None:
        """No arc + 2.0× anomaly → T1=960, T2=960, T3=960."""
        result = _run_step(
            db_session,
            test_user,
            test_entry,
            test_skill,
            troll_multiplier_bp=20000,   # 2.0×
            variety_multiplier_bp=10000,  # 1.0×
        )

        assert "error" not in result
        assert result["total_xp_awarded"] == 960

    def test_variety_multiplier_alone(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill: Skill
    ) -> None:
        """No arc + 1.5× variety → T1=480, T2=720, T3=720."""
        result = _run_step(
            db_session,
            test_user,
            test_entry,
            test_skill,
            troll_multiplier_bp=10000,   # 1.0×
            variety_multiplier_bp=15000,  # 1.5×
        )

        assert "error" not in result
        assert result["total_xp_awarded"] == 720

    def test_arc_does_not_apply_when_instant_quest_skipped_by_confidence(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill: Skill
    ) -> None:
        """Arc multiplier has no effect when instant quest is skipped (confidence below threshold).

        Even a 1.5× redemption arc cannot produce XP if the confidence gate
        prevents the instant quest from being created.
        """
        arc_svc = ArcLifecycleService(db_session)
        arc_svc.create_arc(
            user_id=test_user.id,
            arc_type="redemption",
            xp_reward_multiplier_bp=15000,
            make_active=True,
        )

        # confidence=0.0 < default threshold 0.65 → instant quest skipped
        structured_data = {
            "extraction_confidence_score": 0.0,
            "skills_weights_bp": {test_skill.id: 10000},
            "pattern_hits_json": [],
        }
        step = QuestMatcherStep(db_session)
        result = step.execute(
            user=test_user,
            entry=test_entry,
            structured_data=structured_data,
            troll_multiplier_bp=10000,
            variety_multiplier_bp=10000,
            processing_run_id="arc_quest_test_skip",
        )

        assert result["total_xp_awarded"] == 0
        assert result["instant_quest"] is None
        assert any("INSTANT_SKIPPED" in n for n in result["notes"])


class TestArcReplacementBehaviour:
    """Creating a new arc while one is active replaces the old one correctly."""

    def test_new_arc_replaces_existing_multiplier(
        self, db_session: Session, test_user: User, test_entry: JournalEntry, test_skill: Skill
    ) -> None:
        """The most-recently-activated arc multiplier is the one applied."""
        arc_svc = ArcLifecycleService(db_session)

        # First: redemption arc (1.5×)
        arc_svc.create_arc(
            user_id=test_user.id,
            arc_type="redemption",
            xp_reward_multiplier_bp=15000,
            make_active=True,
        )

        # Second: event arc (1.2×) replaces the redemption arc
        arc_svc.create_arc(
            user_id=test_user.id,
            arc_type="event",
            event_name="low_priority_week",
            xp_reward_multiplier_bp=12000,  # 1.2×
            make_active=True,
        )

        result = _run_step(db_session, test_user, test_entry, test_skill)

        # Active arc is now the event arc (1.2×) not the redemption arc (1.5×)
        # T3 = floor(480 * 12000 / 10000) = 576
        assert result["total_xp_awarded"] == 576
