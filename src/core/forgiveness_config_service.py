"""
Forgiveness configuration resolution service.

Implements Section 4.1.2 (Config Resolution Pipeline) and 4.2.2 (Adaptive Preset).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import Date, cast, func
from sqlalchemy.orm import Session

from src.core.forgiveness_presets import FORGIVENESS_PRESETS, VALID_PRESETS, get_preset_params
from src.db.models.forgiveness import ForgivenessConfig
from src.db.models.user import User
from src.db.models.xp import XpAward


@dataclass(frozen=True)
class EffectiveForgivenessConfig:
    """Effective forgiveness configuration after resolution and adaptive adjustments."""

    preset: str
    skill_decay_rate: float
    skill_grace_days: int
    insight_decay_rate: float
    insight_grace_days: int
    critical_threshold: float


class ForgivenessConfigService:
    """Service for resolving and managing forgiveness configurations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Resolution pipeline (Section 4.1.2)
    # ------------------------------------------------------------------

    def get_or_create_config(self, user_id: str) -> ForgivenessConfig:
        """
        Get or create forgiveness config for a user.

        Resolution order:
        1. Load user row — raise if not found.
        2. If ``users.forgiveness_config_id`` is set, load by that id.
        3. Else fall back to a lookup by ``user_id``.
        4. If still missing, create a default config (preset: balanced) and
           write the pointer back to the user row.
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User not found: {user_id}")

        config: Optional[ForgivenessConfig] = None

        # Step 2 — explicit pointer
        if user.forgiveness_config_id:
            config = (
                self.db.query(ForgivenessConfig)
                .filter(
                    ForgivenessConfig.id == user.forgiveness_config_id,
                    ForgivenessConfig.user_id == user_id,
                )
                .first()
            )

        # Step 3 — user_id fallback
        if config is None:
            config = (
                self.db.query(ForgivenessConfig)
                .filter(ForgivenessConfig.user_id == user_id)
                .first()
            )

        # Step 4 — create default
        if config is None:
            config = self._create_default_config(user_id)
            user.forgiveness_config_id = config.id
            self.db.commit()

        return config

    def _create_default_config(self, user_id: str) -> ForgivenessConfig:
        """Create and persist a default config using the *balanced* preset."""
        params = get_preset_params("balanced")

        config = ForgivenessConfig(
            user_id=user_id,
            preset="balanced",
            skill_decay_rate=params.skill_decay_rate,
            skill_grace_period_days=params.skill_grace_days,
            insight_decay_rate=params.insight_decay_rate,
            insight_grace_period_days=params.insight_grace_days,
            critical_staleness_threshold=params.critical_threshold,
        )

        self.db.add(config)
        return config

    # ------------------------------------------------------------------
    # Effective config resolution (Section 4.2.2)
    # ------------------------------------------------------------------

    def resolve_effective_config(
        self,
        user_id: str,
        now_utc: datetime,
    ) -> EffectiveForgivenessConfig:
        """
        Resolve the effective configuration, applying adaptive adjustments
        when the preset is ``adaptive``.

        For all other presets the stored rates are returned verbatim.
        """
        config = self.get_or_create_config(user_id)

        if config.preset != "adaptive":
            return EffectiveForgivenessConfig(
                preset=config.preset,
                skill_decay_rate=config.skill_decay_rate,
                skill_grace_days=config.skill_grace_period_days,
                insight_decay_rate=config.insight_decay_rate,
                insight_grace_days=config.insight_grace_period_days,
                critical_threshold=config.critical_staleness_threshold,
            )

        # Adaptive: scale rates by activity
        activity_ratio = self._calculate_activity_ratio(user_id, now_utc)
        multiplier = self._get_adaptive_multiplier(activity_ratio)

        return EffectiveForgivenessConfig(
            preset=config.preset,
            skill_decay_rate=min(1.0, config.skill_decay_rate * multiplier),
            skill_grace_days=config.skill_grace_period_days,
            insight_decay_rate=min(1.0, config.insight_decay_rate * multiplier),
            insight_grace_days=config.insight_grace_period_days,
            critical_threshold=config.critical_staleness_threshold,
        )

    def _calculate_activity_ratio(self, user_id: str, now_utc: datetime) -> float:
        """
        Fraction of days in the last 28 days that had at least one XP award.

        Returns a value in [0.0, 1.0].
        """
        window_start = now_utc - timedelta(days=28)

        distinct_days: int = (
            self.db.query(
                func.count(func.distinct(cast(XpAward.awarded_at, Date)))
            )
            .filter(
                XpAward.user_id == user_id,
                XpAward.awarded_at >= window_start,
                XpAward.awarded_at < now_utc,
            )
            .scalar()
            or 0
        )

        return distinct_days / 28.0

    @staticmethod
    def _get_adaptive_multiplier(activity_ratio: float) -> float:
        """
        Map an activity ratio to a decay-rate multiplier.

        >=0.75  → 0.8  (very active — reward with slower decay)
        >=0.45  → 1.0  (normal activity — no adjustment)
        < 0.45  → 1.2  (low activity — gentle nudge with faster decay)
        """
        if activity_ratio >= 0.75:
            return 0.8
        if activity_ratio >= 0.45:
            return 1.0
        return 1.2

    # ------------------------------------------------------------------
    # Preset management
    # ------------------------------------------------------------------

    def update_preset(self, user_id: str, preset: str) -> ForgivenessConfig:
        """
        Change the user's forgiveness preset.

        For any named preset (including ``adaptive`` and ``custom``), this
        validates the name and — for all presets except ``custom`` — resets
        the stored rates to the canonical constants.  The ``custom`` preset
        keeps whatever rates are already stored.
        """
        if preset not in VALID_PRESETS:
            raise ValueError(
                f"Invalid preset: {preset!r}. Valid presets: {sorted(VALID_PRESETS)}"
            )

        config = self.get_or_create_config(user_id)
        config.preset = preset

        if preset != "custom":
            params = get_preset_params(preset)
            config.skill_decay_rate = params.skill_decay_rate
            config.skill_grace_period_days = params.skill_grace_days
            config.insight_decay_rate = params.insight_decay_rate
            config.insight_grace_period_days = params.insight_grace_days
            config.critical_staleness_threshold = params.critical_threshold

        config.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        return config

    def update_custom_params(
        self,
        user_id: str,
        skill_decay_rate: Optional[float] = None,
        skill_grace_days: Optional[int] = None,
        insight_decay_rate: Optional[float] = None,
        insight_grace_days: Optional[int] = None,
        critical_threshold: Optional[float] = None,
    ) -> ForgivenessConfig:
        """
        Update individual parameters for a *custom* preset config.

        Raises ``ValueError`` if the user's current preset is not ``custom``.
        Each argument is optional; only supplied values are written.
        """
        config = self.get_or_create_config(user_id)

        if config.preset != "custom":
            raise ValueError(
                "Can only update custom parameters when preset is 'custom'. "
                f"Current preset: {config.preset!r}"
            )

        if skill_decay_rate is not None:
            if not (0.0 <= skill_decay_rate <= 1.0):
                raise ValueError("skill_decay_rate must be in [0.0, 1.0]")
            config.skill_decay_rate = skill_decay_rate

        if skill_grace_days is not None:
            if skill_grace_days < 0:
                raise ValueError("skill_grace_days must be >= 0")
            config.skill_grace_period_days = skill_grace_days

        if insight_decay_rate is not None:
            if not (0.0 <= insight_decay_rate <= 1.0):
                raise ValueError("insight_decay_rate must be in [0.0, 1.0]")
            config.insight_decay_rate = insight_decay_rate

        if insight_grace_days is not None:
            if insight_grace_days < 0:
                raise ValueError("insight_grace_days must be >= 0")
            config.insight_grace_period_days = insight_grace_days

        if critical_threshold is not None:
            if not (0.0 <= critical_threshold <= 1.0):
                raise ValueError("critical_threshold must be in [0.0, 1.0]")
            config.critical_staleness_threshold = critical_threshold

        config.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        return config
