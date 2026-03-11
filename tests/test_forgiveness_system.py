"""Comprehensive tests for the Week 5 Forgiveness, Balance, and Harmony systems.

Covers:
- ForgivenessPresets: parameter validation for all six presets
- ForgivenessConfigService: config resolution, preset switching, adaptive multiplier, custom params
- ForgivenessDecayService: skill staleness, insight decay, reinforcement helpers, decay snapshots
- VarietyService: score calculation, bonus formula, XP application
- DiminishingReturnsService: streak management, penalty calculation
- HarmonyScoringService: overwork detection, read-only vs. advance semantics
- HarmonyClassifier: 3-tier dimension classification
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401  — registers all models with Base.metadata
from src.db.base import Base
from src.db.models.forgiveness import ForgivenessConfig
from src.db.models.harmony import HarmonyDimension
from src.db.models.insight import Insight
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.skill import Skill
from src.db.models.strategy import StrategyTracking
from src.db.models.user import User


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


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


def _make_user(
    db: Session,
    *,
    user_id: str = "u-test",
    timezone_name: str = "UTC",
) -> User:
    user = User(
        id=user_id,
        username=f"user-{user_id}",
        email=f"{user_id}@example.com",
        password_hash="hash",
        timezone=timezone_name,
        home_country="US",
    )
    db.add(user)
    db.commit()
    return user


def _attach_config(
    db: Session,
    user: User,
    *,
    preset: str = "balanced",
    skill_decay_rate: float = 0.05,
    insight_decay_rate: float = 0.10,
    skill_grace_days: int = 7,
    insight_grace_days: int = 3,
    critical_threshold: float = 0.80,
) -> ForgivenessConfig:
    config = ForgivenessConfig(
        user_id=user.id,
        preset=preset,
        skill_decay_rate=skill_decay_rate,
        insight_decay_rate=insight_decay_rate,
        skill_grace_period_days=skill_grace_days,
        insight_grace_period_days=insight_grace_days,
        critical_staleness_threshold=critical_threshold,
    )
    db.add(config)
    db.flush()
    user.forgiveness_config_id = config.id
    db.commit()
    return config


def _make_skill(
    db: Session,
    user_id: str,
    *,
    staleness: float = 0.0,
    last_activity_at: datetime | None = None,
    decay_paused: bool = False,
) -> Skill:
    skill = Skill(
        user_id=user_id,
        name="Test Skill",
        canonical_name="test_skill",
        staleness=staleness,
        last_activity_at=last_activity_at,
        decay_paused=decay_paused,
    )
    db.add(skill)
    db.commit()
    return skill


def _make_insight(
    db: Session,
    user_id: str,
    *,
    strength: float = 1.0,
    created_at: datetime | None = None,
    last_reinforced_at: datetime | None = None,
) -> Insight:
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    insight = Insight(
        user_id=user_id,
        insight_type="pattern",
        title="Test Insight",
        description="A test insight",
        strength=strength,
        created_at=created_at,
        last_reinforced_at=last_reinforced_at,
        status="active",
    )
    db.add(insight)
    db.commit()
    return insight


# ===========================================================================
# Section 1: Forgiveness Presets
# ===========================================================================


class TestForgivenessPresets:
    """Tests for src.core.forgiveness_presets."""

    def test_balanced_preset_has_correct_params(self) -> None:
        from src.core.forgiveness_presets import get_preset_params

        p = get_preset_params("balanced")
        assert p.skill_decay_rate == 0.05
        assert p.skill_grace_days == 7
        assert p.insight_decay_rate == 0.10
        assert p.insight_grace_days == 3
        assert p.critical_threshold == 0.80

    def test_hardcore_preset_is_stricter_than_balanced(self) -> None:
        from src.core.forgiveness_presets import get_preset_params

        b = get_preset_params("balanced")
        h = get_preset_params("hardcore")
        assert h.skill_decay_rate > b.skill_decay_rate
        assert h.skill_grace_days < b.skill_grace_days
        assert h.insight_decay_rate > b.insight_decay_rate
        assert h.insight_grace_days < b.insight_grace_days
        assert h.critical_threshold < b.critical_threshold

    def test_lenient_preset_is_softer_than_balanced(self) -> None:
        from src.core.forgiveness_presets import get_preset_params

        b = get_preset_params("balanced")
        l = get_preset_params("lenient")
        assert l.skill_decay_rate < b.skill_decay_rate
        assert l.skill_grace_days > b.skill_grace_days
        assert l.insight_decay_rate < b.insight_decay_rate
        assert l.insight_grace_days > b.insight_grace_days

    def test_zen_preset_has_minimal_decay(self) -> None:
        from src.core.forgiveness_presets import get_preset_params

        z = get_preset_params("zen")
        assert z.skill_decay_rate == pytest.approx(0.01)
        assert z.skill_grace_days == 14
        assert z.insight_grace_days == 7

    def test_all_six_presets_are_accessible(self) -> None:
        from src.core.forgiveness_presets import get_preset_params

        for preset_name in ("balanced", "hardcore", "lenient", "zen", "adaptive", "custom"):
            params = get_preset_params(preset_name)
            assert params is not None
            assert 0.0 <= params.skill_decay_rate <= 1.0

    def test_invalid_preset_raises_value_error(self) -> None:
        from src.core.forgiveness_presets import get_preset_params

        with pytest.raises(ValueError, match="Unknown forgiveness preset"):
            get_preset_params("nonexistent")

    def test_all_presets_have_display_names(self) -> None:
        from src.core.forgiveness_presets import get_preset_name

        for preset_name in ("balanced", "hardcore", "lenient", "zen", "adaptive", "custom"):
            name = get_preset_name(preset_name)
            assert isinstance(name, str)
            assert len(name) > 0


# ===========================================================================
# Section 2: ForgivenessConfigService
# ===========================================================================


class TestForgivenessConfigService:
    """Tests for src.core.forgiveness_config_service.ForgivenessConfigService."""

    def test_get_or_create_auto_creates_default_balanced_config(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        user = _make_user(db_session, user_id="u-config-new")
        service = ForgivenessConfigService(db_session)

        config = service.get_or_create_config(user.id)

        assert config.preset == "balanced"
        assert config.skill_decay_rate == pytest.approx(0.05)
        assert config.skill_grace_period_days == 7
        assert config.insight_decay_rate == pytest.approx(0.10)
        assert config.insight_grace_period_days == 3
        assert config.critical_staleness_threshold == pytest.approx(0.80)
        # Pointer written back to user row
        db_session.refresh(user)
        assert user.forgiveness_config_id == config.id

    def test_get_or_create_reuses_existing_config(self, db_session: Session) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        user = _make_user(db_session, user_id="u-config-existing")
        _attach_config(db_session, user, preset="lenient")
        service = ForgivenessConfigService(db_session)

        config1 = service.get_or_create_config(user.id)
        config2 = service.get_or_create_config(user.id)

        assert config1.id == config2.id
        assert config1.preset == "lenient"

    def test_get_or_create_raises_for_unknown_user(self, db_session: Session) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        service = ForgivenessConfigService(db_session)
        with pytest.raises(ValueError, match="User not found"):
            service.get_or_create_config("no-such-user")

    def test_update_preset_writes_canonical_rates(self, db_session: Session) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService
        from src.core.forgiveness_presets import get_preset_params

        user = _make_user(db_session, user_id="u-preset-update")
        service = ForgivenessConfigService(db_session)

        config = service.update_preset(user.id, "zen")

        zen = get_preset_params("zen")
        assert config.preset == "zen"
        assert config.skill_decay_rate == pytest.approx(zen.skill_decay_rate)
        assert config.skill_grace_period_days == zen.skill_grace_days
        assert config.insight_decay_rate == pytest.approx(zen.insight_decay_rate)

    def test_update_preset_raises_for_invalid_preset(self, db_session: Session) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        user = _make_user(db_session, user_id="u-bad-preset")
        service = ForgivenessConfigService(db_session)

        with pytest.raises(ValueError, match="Invalid preset"):
            service.update_preset(user.id, "godmode")

    def test_adaptive_multiplier_low_activity_returns_1_2(self) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        assert ForgivenessConfigService._get_adaptive_multiplier(0.0) == pytest.approx(1.2)
        assert ForgivenessConfigService._get_adaptive_multiplier(0.44) == pytest.approx(1.2)

    def test_adaptive_multiplier_normal_activity_returns_1_0(self) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        assert ForgivenessConfigService._get_adaptive_multiplier(0.45) == pytest.approx(1.0)
        assert ForgivenessConfigService._get_adaptive_multiplier(0.74) == pytest.approx(1.0)

    def test_adaptive_multiplier_high_activity_returns_0_8(self) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        assert ForgivenessConfigService._get_adaptive_multiplier(0.75) == pytest.approx(0.8)
        assert ForgivenessConfigService._get_adaptive_multiplier(1.0) == pytest.approx(0.8)

    def test_resolve_effective_config_applies_adaptive_multiplier_for_low_activity(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        user = _make_user(db_session, user_id="u-adaptive-low")
        _attach_config(db_session, user, preset="adaptive", skill_decay_rate=0.05)
        service = ForgivenessConfigService(db_session)

        # No XP awards in window → activity_ratio == 0.0 → multiplier == 1.2
        now_utc = datetime.now(timezone.utc)
        effective = service.resolve_effective_config(user.id, now_utc)

        assert effective.preset == "adaptive"
        assert effective.skill_decay_rate == pytest.approx(0.05 * 1.2)

    def test_resolve_effective_config_returns_stored_rates_for_non_adaptive(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        user = _make_user(db_session, user_id="u-lenient-resolve")
        _attach_config(
            db_session, user, preset="lenient", skill_decay_rate=0.03, skill_grace_days=10
        )
        service = ForgivenessConfigService(db_session)

        effective = service.resolve_effective_config(user.id, datetime.now(timezone.utc))

        assert effective.preset == "lenient"
        assert effective.skill_decay_rate == pytest.approx(0.03)
        assert effective.skill_grace_days == 10

    def test_update_custom_params_raises_when_preset_is_not_custom(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        user = _make_user(db_session, user_id="u-non-custom")
        _attach_config(db_session, user, preset="balanced")
        service = ForgivenessConfigService(db_session)

        with pytest.raises(ValueError, match="custom"):
            service.update_custom_params(user.id, skill_decay_rate=0.07)

    def test_update_custom_params_applies_individual_fields(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        user = _make_user(db_session, user_id="u-custom-params")
        _attach_config(db_session, user, preset="custom", skill_decay_rate=0.05)
        service = ForgivenessConfigService(db_session)

        config = service.update_custom_params(user.id, skill_decay_rate=0.07, skill_grace_days=5)

        assert config.skill_decay_rate == pytest.approx(0.07)
        assert config.skill_grace_period_days == 5

    def test_update_custom_params_rejects_out_of_range_decay_rate(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        user = _make_user(db_session, user_id="u-custom-bad-rate")
        _attach_config(db_session, user, preset="custom")
        service = ForgivenessConfigService(db_session)

        with pytest.raises(ValueError, match="skill_decay_rate"):
            service.update_custom_params(user.id, skill_decay_rate=1.5)

    def test_update_custom_params_rejects_negative_grace_days(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_config_service import ForgivenessConfigService

        user = _make_user(db_session, user_id="u-custom-bad-grace")
        _attach_config(db_session, user, preset="custom")
        service = ForgivenessConfigService(db_session)

        with pytest.raises(ValueError, match="grace_days"):
            service.update_custom_params(user.id, skill_grace_days=-1)


# ===========================================================================
# Section 3: ForgivenessDecayService — Skills
# ===========================================================================


class TestForgivenessDecaySkills:
    """Staleness decay and reinforcement for Skill rows."""

    def test_skill_staleness_increases_after_grace_period(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-decay-skill")
        _attach_config(db_session, user)
        # last activity 10 days ago; grace = 7 → effective_days = 3
        last_active = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        skill = _make_skill(db_session, user.id, staleness=0.0, last_activity_at=last_active)
        service = ForgivenessDecayService(db_session)

        now = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        metrics = service.decay_skills(user.id, now)
        db_session.refresh(skill)

        # staleness = 1 - exp(-0.05 * 3) ≈ 0.139
        expected = 1.0 - math.exp(-0.05 * 3)
        assert skill.staleness == pytest.approx(expected, abs=1e-6)
        assert metrics["skills_decayed"] == 1

    def test_skill_in_grace_period_stays_at_zero(self, db_session: Session) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-grace-skill")
        _attach_config(db_session, user)
        # last activity 3 days ago — within 7-day grace
        last_active = datetime(2026, 3, 8, 0, 0, tzinfo=timezone.utc)
        skill = _make_skill(db_session, user.id, staleness=0.0, last_activity_at=last_active)
        service = ForgivenessDecayService(db_session)

        now = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        service.decay_skills(user.id, now)
        db_session.refresh(skill)

        assert skill.staleness == 0.0

    def test_staleness_max_rule_prevents_decrease(self, db_session: Session) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-max-rule")
        _attach_config(db_session, user)
        # Skill already at 0.5 staleness; computed staleness for 3 effective days ≈ 0.139 < 0.5
        last_active = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
        skill = _make_skill(db_session, user.id, staleness=0.5, last_activity_at=last_active)
        service = ForgivenessDecayService(db_session)

        # 10 days inactive but currently stored staleness = 0.5
        now = datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)  # only 3 days, within grace
        service.decay_skills(user.id, now)
        db_session.refresh(skill)

        # computed staleness would be 0.0 (within grace), but stored value was 0.5 → stays 0.5
        assert skill.staleness == pytest.approx(0.5)

    def test_decay_paused_skill_is_skipped(self, db_session: Session) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-paused-skill")
        _attach_config(db_session, user)
        last_active = datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc)
        skill = _make_skill(
            db_session, user.id, staleness=0.0, last_activity_at=last_active, decay_paused=True
        )
        service = ForgivenessDecayService(db_session)

        now = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        metrics = service.decay_skills(user.id, now)
        db_session.refresh(skill)

        assert skill.staleness == 0.0
        assert metrics["skills_processed"] == 0

    def test_skill_with_no_last_activity_stays_at_zero(self, db_session: Session) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-no-activity")
        _attach_config(db_session, user)
        skill = _make_skill(db_session, user.id, staleness=0.0, last_activity_at=None)
        service = ForgivenessDecayService(db_session)

        now = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        service.decay_skills(user.id, now)
        db_session.refresh(skill)

        assert skill.staleness == 0.0

    def test_reinforce_skill_primary_applies_0_25_multiplier(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-reinforce-primary")
        skill = _make_skill(db_session, user.id, staleness=0.8)
        service = ForgivenessDecayService(db_session)
        now = datetime(2026, 3, 11, tzinfo=timezone.utc)

        service.reinforce_skill(skill, now, is_primary=True, xp_amount=500)

        assert skill.staleness == pytest.approx(0.8 * 0.25)
        assert skill.last_activity_at == now

    def test_reinforce_skill_secondary_applies_0_50_multiplier(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-reinforce-secondary")
        skill = _make_skill(db_session, user.id, staleness=0.8)
        service = ForgivenessDecayService(db_session)
        now = datetime(2026, 3, 11, tzinfo=timezone.utc)

        service.reinforce_skill(skill, now, is_primary=False, xp_amount=100)

        assert skill.staleness == pytest.approx(0.8 * 0.50)

    def test_reinforce_skill_paused_skill_only_updates_timestamp(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-paused-reinforce")
        skill = _make_skill(db_session, user.id, staleness=0.6, decay_paused=True)
        service = ForgivenessDecayService(db_session)
        now = datetime(2026, 3, 11, tzinfo=timezone.utc)

        service.reinforce_skill(skill, now)

        # Staleness unchanged when paused; timestamp updated
        assert skill.staleness == pytest.approx(0.6)
        assert skill.last_activity_at == now


# ===========================================================================
# Section 4: ForgivenessDecayService — Insights
# ===========================================================================


class TestForgivenessDecayInsights:
    """Strength decay and reinforcement for Insight rows."""

    def test_insight_decay_reduces_strength_after_grace_period(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-decay-insight")
        _attach_config(db_session, user)
        # Created 10 days ago; insight grace = 3 → effective_days = 7
        created_at = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
        insight = _make_insight(db_session, user.id, strength=1.0, created_at=created_at)
        service = ForgivenessDecayService(db_session)

        now = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        metrics = service.decay_insights(user.id, now)
        db_session.refresh(insight)

        # strength = exp(-0.10 * 7) ≈ 0.496
        expected = math.exp(-0.10 * 7)
        assert insight.strength == pytest.approx(expected, abs=1e-4)
        assert metrics["insights_decayed"] == 1

    def test_insight_within_grace_period_retains_full_strength(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-grace-insight")
        _attach_config(db_session, user)
        # Created 2 days ago — within 3-day insight grace
        created_at = datetime(2026, 3, 9, 0, 0, tzinfo=timezone.utc)
        insight = _make_insight(db_session, user.id, strength=1.0, created_at=created_at)
        service = ForgivenessDecayService(db_session)

        now = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        service.decay_insights(user.id, now)
        db_session.refresh(insight)

        # effective_days = 0 → strength = exp(0) = 1.0
        assert insight.strength == pytest.approx(1.0)

    def test_reinforce_insight_increases_strength_by_0_20(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-reinforce-insight")
        insight = _make_insight(db_session, user.id, strength=0.60)
        service = ForgivenessDecayService(db_session)
        now = datetime(2026, 3, 11, tzinfo=timezone.utc)

        service.reinforce_insight(insight, now)

        assert insight.strength == pytest.approx(0.80)
        assert insight.last_reinforced_at == now

    def test_reinforce_insight_caps_strength_at_1_0(self, db_session: Session) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-reinforce-insight-cap")
        insight = _make_insight(db_session, user.id, strength=0.95)
        service = ForgivenessDecayService(db_session)

        service.reinforce_insight(insight, datetime(2026, 3, 11, tzinfo=timezone.utc))

        assert insight.strength == pytest.approx(1.0)

    def test_insight_last_reinforced_at_overrides_created_at_for_decay(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-insight-reinforced-grace")
        _attach_config(db_session, user)
        created_old = datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc)
        last_reinforced_recent = datetime(2026, 3, 9, 0, 0, tzinfo=timezone.utc)
        insight = _make_insight(
            db_session,
            user.id,
            strength=1.0,
            created_at=created_old,
            last_reinforced_at=last_reinforced_recent,
        )
        service = ForgivenessDecayService(db_session)

        now = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        service.decay_insights(user.id, now)
        db_session.refresh(insight)

        # last_reinforced is only 2 days before now; grace=3 → effective_days=0 → strength=1.0
        assert insight.strength == pytest.approx(1.0)


# ===========================================================================
# Section 5: ForgivenessDecayService — Decay Snapshots
# ===========================================================================


class TestForgivenessDecaySnapshots:
    """Decay snapshot creation and idempotency."""

    def test_create_decay_snapshot_aggregates_skill_staleness(
        self, db_session: Session
    ) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService

        user = _make_user(db_session, user_id="u-snapshot-1")
        _attach_config(db_session, user)
        last_active = datetime(2026, 3, 1, tzinfo=timezone.utc)
        # Two skills with distinct canonical_names (UNIQUE constraint on user_id + canonical_name)
        skill_a = Skill(
            user_id=user.id, name="Skill A", canonical_name="skill_a",
            staleness=0.2, last_activity_at=last_active,
        )
        skill_b = Skill(
            user_id=user.id, name="Skill B", canonical_name="skill_b",
            staleness=0.4, last_activity_at=last_active,
        )
        db_session.add_all([skill_a, skill_b])
        db_session.commit()
        service = ForgivenessDecayService(db_session)

        now = datetime(2026, 3, 11, tzinfo=timezone.utc)
        snapshot = service.create_decay_snapshot(user.id, now.date(), now)

        assert snapshot.average_skill_staleness == pytest.approx(0.3, abs=0.01)

    def test_create_decay_snapshot_is_idempotent(self, db_session: Session) -> None:
        from src.core.forgiveness_decay_service import ForgivenessDecayService
        from src.db.models.forgiveness import DecaySnapshot

        user = _make_user(db_session, user_id="u-snapshot-idem")
        _attach_config(db_session, user)
        last_active = datetime(2026, 3, 1, tzinfo=timezone.utc)
        _make_skill(db_session, user.id, staleness=0.3, last_activity_at=last_active)
        service = ForgivenessDecayService(db_session)

        now = datetime(2026, 3, 11, tzinfo=timezone.utc)
        snap1 = service.create_decay_snapshot(user.id, now.date(), now)
        snap2 = service.create_decay_snapshot(user.id, now.date(), now)

        # Should update the same row, not create a second one
        total = (
            db_session.query(DecaySnapshot)
            .filter(
                DecaySnapshot.user_id == user.id,
                DecaySnapshot.snapshot_date == now.date().isoformat(),
            )
            .count()
        )
        assert total == 1
        assert snap1.id == snap2.id


# ===========================================================================
# Section 6: Balance — VarietyService
# ===========================================================================


class TestVarietyService:
    """Tests for src.core.balance_variety_service.VarietyService."""

    def test_equal_distribution_yields_score_near_one(
        self, db_session: Session
    ) -> None:
        from src.core.balance_variety_service import VarietyService

        service = VarietyService(db_session)
        equal_counts = {k: 10 for k in ("social", "study", "mundane", "troll", "grind", "harmony")}
        score = service.calculate_variety_score(equal_counts)
        assert score == pytest.approx(1.0, abs=1e-6)

    def test_single_strategy_yields_score_near_zero(
        self, db_session: Session
    ) -> None:
        from src.core.balance_variety_service import VarietyService

        service = VarietyService(db_session)
        grind_only = {"social": 0, "study": 0, "mundane": 0, "troll": 0, "grind": 60, "harmony": 0}
        score = service.calculate_variety_score(grind_only)
        assert score == pytest.approx(0.0, abs=1e-6)

    def test_empty_counts_yields_zero_score(self, db_session: Session) -> None:
        from src.core.balance_variety_service import VarietyService

        service = VarietyService(db_session)
        score = service.calculate_variety_score({k: 0 for k in ("social", "study", "mundane", "troll", "grind", "harmony")})
        assert score == 0.0

    def test_variety_bonus_pct_uses_quadratic_formula(
        self, db_session: Session
    ) -> None:
        from src.core.balance_variety_service import VarietyService

        service = VarietyService(db_session)
        # bonus_pct = score² × 0.30
        assert service.calculate_variety_bonus_pct(0.0) == pytest.approx(0.0)
        assert service.calculate_variety_bonus_pct(0.5) == pytest.approx(0.5 ** 2 * 0.30)
        assert service.calculate_variety_bonus_pct(1.0) == pytest.approx(0.30)

    def test_variety_multiplier_bp_range(self, db_session: Session) -> None:
        from src.core.balance_variety_service import VarietyService

        service = VarietyService(db_session)
        assert service.calculate_variety_multiplier_bp(0.0) == 10000
        assert service.calculate_variety_multiplier_bp(0.30) == 13000

    def test_apply_variety_bonus_to_xp(self, db_session: Session) -> None:
        from src.core.balance_variety_service import VarietyService

        service = VarietyService(db_session)
        # 100 XP with 30% bonus → 130
        result = service.apply_variety_bonus_to_xp(100, 0.30)
        assert result == 130

    def test_apply_variety_multiplier_bp_integer_arithmetic(
        self, db_session: Session
    ) -> None:
        from src.core.balance_variety_service import VarietyService

        service = VarietyService(db_session)
        # 100 * 13000 // 10000 = 130
        assert service.apply_variety_multiplier_bp(100, 13000) == 130
        # 100 * 10750 // 10000 = 107
        assert service.apply_variety_multiplier_bp(100, 10750) == 107


# ===========================================================================
# Section 7: Balance — DiminishingReturnsService
# ===========================================================================


class TestDiminishingReturnsService:
    """Tests for src.core.balance_diminishing_returns.DiminishingReturnsService."""

    def _make_tracking_with_streaks(
        self, db: Session, user_id: str, streaks_json: str
    ) -> StrategyTracking:
        tracking = StrategyTracking(
            user_id=user_id,
            strategy_streaks_json=streaks_json,
        )
        db.add(tracking)
        db.commit()
        return tracking

    def test_penalty_is_1_0_for_new_strategy(self, db_session: Session) -> None:
        from src.core.balance_diminishing_returns import DiminishingReturnsService

        user = _make_user(db_session, user_id="u-dr-new")
        tracking = self._make_tracking_with_streaks(db_session, user.id, "{}")
        service = DiminishingReturnsService(db_session)

        assert service.get_strategy_penalty("study", tracking) == pytest.approx(1.0)

    def test_penalty_at_streak_2_is_still_1_0(self, db_session: Session) -> None:
        from src.core.balance_diminishing_returns import DiminishingReturnsService

        user = _make_user(db_session, user_id="u-dr-streak2")
        streaks = json.dumps({"study": {"count": 2, "last_day": "2026-03-10"}})
        tracking = self._make_tracking_with_streaks(db_session, user.id, streaks)
        service = DiminishingReturnsService(db_session)

        # max(0.75, 1.0 - 0.05 * max(0, 2 - 2)) = 1.0
        assert service.get_strategy_penalty("study", tracking) == pytest.approx(1.0)

    def test_penalty_at_streak_4_is_0_90(self, db_session: Session) -> None:
        from src.core.balance_diminishing_returns import DiminishingReturnsService

        user = _make_user(db_session, user_id="u-dr-streak4")
        streaks = json.dumps({"study": {"count": 4, "last_day": "2026-03-10"}})
        tracking = self._make_tracking_with_streaks(db_session, user.id, streaks)
        service = DiminishingReturnsService(db_session)

        # max(0.75, 1.0 - 0.05 * 2) = 0.90
        assert service.get_strategy_penalty("study", tracking) == pytest.approx(0.90)

    def test_penalty_floor_is_0_75_for_long_streaks(self, db_session: Session) -> None:
        from src.core.balance_diminishing_returns import DiminishingReturnsService

        user = _make_user(db_session, user_id="u-dr-floor")
        streaks = json.dumps({"grind": {"count": 20, "last_day": "2026-03-10"}})
        tracking = self._make_tracking_with_streaks(db_session, user.id, streaks)
        service = DiminishingReturnsService(db_session)

        # Would be 1.0 - 0.05 * 18 = 0.10 but floor = 0.75
        assert service.get_strategy_penalty("grind", tracking) == pytest.approx(0.75)

    def test_update_strategy_streaks_increments_on_consecutive_day(
        self, db_session: Session
    ) -> None:
        from src.core.balance_diminishing_returns import DiminishingReturnsService

        user = _make_user(db_session, user_id="u-dr-consecutive")
        streaks = json.dumps({"study": {"count": 3, "last_day": "2026-03-10"}})
        tracking = self._make_tracking_with_streaks(db_session, user.id, streaks)
        service = DiminishingReturnsService(db_session)

        service.update_strategy_streaks(
            user_id=user.id,
            strategies_today=["study"],
            today_local=date(2026, 3, 11),
            tracking=tracking,
        )

        updated = json.loads(tracking.strategy_streaks_json)
        assert updated["study"]["count"] == 4
        assert updated["study"]["last_day"] == "2026-03-11"

    def test_update_strategy_streaks_resets_on_gap(self, db_session: Session) -> None:
        from src.core.balance_diminishing_returns import DiminishingReturnsService

        user = _make_user(db_session, user_id="u-dr-gap")
        streaks = json.dumps({"grind": {"count": 5, "last_day": "2026-03-05"}})
        tracking = self._make_tracking_with_streaks(db_session, user.id, streaks)
        service = DiminishingReturnsService(db_session)

        # Gap of 6 days → reset to 1
        service.update_strategy_streaks(
            user_id=user.id,
            strategies_today=["grind"],
            today_local=date(2026, 3, 11),
            tracking=tracking,
        )

        updated = json.loads(tracking.strategy_streaks_json)
        assert updated["grind"]["count"] == 1

    def test_update_strategy_streaks_is_idempotent_within_same_day(
        self, db_session: Session
    ) -> None:
        from src.core.balance_diminishing_returns import DiminishingReturnsService

        user = _make_user(db_session, user_id="u-dr-idempotent")
        streaks = json.dumps({"study": {"count": 3, "last_day": "2026-03-11"}})
        tracking = self._make_tracking_with_streaks(db_session, user.id, streaks)
        service = DiminishingReturnsService(db_session)

        service.update_strategy_streaks(
            user_id=user.id,
            strategies_today=["study"],
            today_local=date(2026, 3, 11),
            tracking=tracking,
        )

        updated = json.loads(tracking.strategy_streaks_json)
        # Count must not have increased (already credited today)
        assert updated["study"]["count"] == 3


# ===========================================================================
# Section 8: Harmony — HarmonyClassifier
# ===========================================================================


class TestHarmonyClassifier:
    """Tests for src.core.harmony_classifier.HarmonyClassifier."""

    def _make_entry(self, db: Session, user_id: str, content: str) -> JournalEntry:
        entry = JournalEntry(
            user_id=user_id,
            content=content,
            entry_type="text",
            status="completed",
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        db.commit()
        return entry

    def _make_structured(self, entry: JournalEntry, *, task_type: str | None = None) -> object:
        return type(
            "_S",
            (),
            {
                "task_type": task_type,
                "skills_themes_involved": None,
                "canonical_text": entry.content,
            },
        )()

    def test_task_type_tier_maps_rest_to_rest_dimension(
        self, db_session: Session
    ) -> None:
        from src.core.harmony_classifier import HarmonyClassifier

        user = _make_user(db_session, user_id="u-cls-rest")
        entry = self._make_entry(db_session, user.id, "Slept in and recovered")
        structured = self._make_structured(entry, task_type="rest")
        classifier = HarmonyClassifier(db_session)

        dims = classifier.classify_dimensions(entry, structured)

        assert "rest" in dims
        assert "productivity" not in dims

    def test_task_type_tier_maps_analytical_to_mental_and_productivity(
        self, db_session: Session
    ) -> None:
        from src.core.harmony_classifier import HarmonyClassifier

        user = _make_user(db_session, user_id="u-cls-analytical")
        entry = self._make_entry(db_session, user.id, "Deep coding session")
        structured = self._make_structured(entry, task_type="analytical")
        classifier = HarmonyClassifier(db_session)

        dims = classifier.classify_dimensions(entry, structured)

        assert "mental" in dims
        assert "productivity" in dims

    def test_keyword_fallback_detects_physical_dimension(
        self, db_session: Session
    ) -> None:
        from src.core.harmony_classifier import HarmonyClassifier

        user = _make_user(db_session, user_id="u-cls-keyword")
        entry = self._make_entry(db_session, user.id, "Went for a run and workout at gym")
        structured = self._make_structured(entry, task_type=None)
        classifier = HarmonyClassifier(db_session)

        dims = classifier.classify_dimensions(entry, structured)

        assert "physical" in dims

    def test_task_type_tier_takes_precedence_over_keywords(
        self, db_session: Session
    ) -> None:
        from src.core.harmony_classifier import HarmonyClassifier

        user = _make_user(db_session, user_id="u-cls-precedence")
        # Content has physical keywords but task_type is "social"
        entry = self._make_entry(db_session, user.id, "Ran with friends at the gym")
        structured = self._make_structured(entry, task_type="social")
        classifier = HarmonyClassifier(db_session)

        dims = classifier.classify_dimensions(entry, structured)

        assert "social" in dims
        # Should not also include physical via keywords since task_type tier returned early
        assert "physical" not in dims


# ===========================================================================
# Section 9: Harmony — HarmonyScoringService
# ===========================================================================


class TestHarmonyScoringService:
    """Tests for overwork detection and overall balance calculation."""

    def test_no_overwork_when_rest_is_adequate(self, db_session: Session) -> None:
        from src.core.harmony_scoring_service import HarmonyScoringService

        user = _make_user(db_session, user_id="u-no-overwork")
        _attach_config(db_session, user)
        harmony = HarmonyDimension(
            user_id=user.id,
            physical=0.8,
            mental=0.7,
            social=0.6,
            productivity=0.90,
            rest=0.60,  # rest > 0.35 threshold
            growth=0.7,
            creative=0.6,
        )
        db_session.add(harmony)
        db_session.commit()

        service = HarmonyScoringService(db_session)
        status = service.advance_overwork_state(
            harmony,
            user_id=user.id,
            today_local=date(2026, 3, 11),
            now_utc=datetime(2026, 3, 11, 10, 0, tzinfo=timezone.utc),
            average_energy=7.0,
        )

        assert status.condition is False
        assert status.stage == 0

    def test_overwork_condition_triggers_when_productivity_high_rest_low(
        self, db_session: Session
    ) -> None:
        from src.core.harmony_scoring_service import HarmonyScoringService

        user = _make_user(db_session, user_id="u-overwork-warn")
        _attach_config(db_session, user)
        harmony = HarmonyDimension(
            user_id=user.id,
            physical=0.7,
            mental=0.8,
            social=0.8,
            productivity=0.90,  # >= 0.85
            rest=0.30,           # <= 0.35
            growth=0.8,
            creative=0.7,
        )
        db_session.add(harmony)
        db_session.commit()

        service = HarmonyScoringService(db_session)
        status = service.advance_overwork_state(
            harmony,
            user_id=user.id,
            today_local=date(2026, 3, 11),
            now_utc=datetime(2026, 3, 11, 10, 0, tzinfo=timezone.utc),
            average_energy=6.0,
        )

        assert status.condition is True
        assert status.recommended_stage >= 1

    def test_read_only_status_does_not_mutate_consecutive_days(
        self, db_session: Session
    ) -> None:
        from src.core.harmony_scoring_service import HarmonyScoringService

        user = _make_user(db_session, user_id="u-overwork-readonly")
        _attach_config(db_session, user)
        harmony = HarmonyDimension(
            user_id=user.id,
            productivity=0.90,
            rest=0.25,
            physical=0.5,
            overwork_consecutive_days=3,
            overwork_stage=1,
        )
        db_session.add(harmony)
        db_session.commit()

        service = HarmonyScoringService(db_session)
        status = service.get_read_only_overwork_status(
            harmony,
            average_energy=5.0,
            preset="balanced",
        )

        # Read-only call must not change DB row
        db_session.refresh(harmony)
        assert harmony.overwork_consecutive_days == 3
        assert harmony.overwork_stage == 1

    def test_overwork_deescalates_after_recovery_day(self, db_session: Session) -> None:
        from src.core.harmony_scoring_service import HarmonyScoringService

        user = _make_user(db_session, user_id="u-recovery")
        _attach_config(db_session, user)
        harmony = HarmonyDimension(
            user_id=user.id,
            physical=0.7,
            mental=0.7,
            social=0.7,
            productivity=0.40,  # Low productivity = no overwork condition
            rest=0.80,
            growth=0.7,
            creative=0.7,
            overwork_stage=2,
            overwork_consecutive_days=5,
        )
        db_session.add(harmony)
        db_session.commit()

        service = HarmonyScoringService(db_session)
        status = service.advance_overwork_state(
            harmony,
            user_id=user.id,
            today_local=date(2026, 3, 11),
            now_utc=datetime(2026, 3, 11, 10, 0, tzinfo=timezone.utc),
            average_energy=8.0,
        )

        assert status.condition is False
        assert status.stage < 2

    def test_calculate_overall_balance_penalises_high_variance(
        self, db_session: Session
    ) -> None:
        from src.core.harmony_scoring_service import HarmonyScoringService

        user = _make_user(db_session, user_id="u-balance-calc")
        service = HarmonyScoringService(db_session)

        # All equal → high balance
        balanced = {"physical": 0.7, "mental": 0.7, "social": 0.7,
                    "productivity": 0.7, "rest": 0.7, "growth": 0.7, "creative": 0.7}
        # Skewed → lower balance
        skewed = {"physical": 0.1, "mental": 0.9, "social": 0.1,
                  "productivity": 0.9, "rest": 0.1, "growth": 0.9, "creative": 0.1}

        balanced_score = service.calculate_overall_balance(balanced)
        skewed_score = service.calculate_overall_balance(skewed)

        assert balanced_score > skewed_score
        assert 0.0 <= balanced_score <= 1.0
        assert 0.0 <= skewed_score <= 1.0
