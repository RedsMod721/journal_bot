"""
Recovery detection and redemption transition.

Implements Section 8.6.3 (Regression completion) from architecture.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models.story import ArcTrigger, StoryArc
from src.db.models.user import User
from src.core.arc_lifecycle import ArcLifecycleService
from src.core.arc_regression_trigger import RegressionTriggerService
from src.core.arc_timestamps import now_utc_fixed_ms


# Default thresholds (configurable)
DEFAULT_RECOVERY_IMPROVEMENT_THRESHOLD: float = 0.30
DEFAULT_RECOVERY_ABSOLUTE_STALENESS_THRESHOLD: float = 0.25
DEFAULT_REGRESSION_SAFETY_VALVE_DAYS: float = 60.0
_MIN_DAYS_ACTIVE: float = 7.0


class RecoveryDetectionService:
    """Detect recovery and transition regression → redemption (Section 8.6.3)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.lifecycle = ArcLifecycleService(db)
        self.regression_trigger = RegressionTriggerService(db)

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def check_and_transition_to_redemption(
        self,
        user_id: str,
        recovery_improvement_threshold: float = DEFAULT_RECOVERY_IMPROVEMENT_THRESHOLD,
        recovery_absolute_staleness_threshold: float = DEFAULT_RECOVERY_ABSOLUTE_STALENESS_THRESHOLD,
    ) -> Optional[StoryArc]:
        """Check recovery criteria and transition regression → redemption.

        Section 8.6.3: Regression completion criteria (all must be true):
          - days_active >= 7.0
          - improvement_ratio >= recovery_improvement_threshold (default 0.30)
          - current_avg_staleness <= recovery_absolute_staleness_threshold (default 0.25)

        Returns:
            Redemption arc if transition occurred, None otherwise.
        """
        active_arc = self.lifecycle.get_active_arc(user_id)

        if not active_arc or active_arc.arc_type != "regression":
            return None

        days_active = self.lifecycle.calculate_days_active(active_arc)

        # Safety valve check (before minimum days — valve takes priority)
        if days_active >= DEFAULT_REGRESSION_SAFETY_VALVE_DAYS:
            self._apply_safety_valve(active_arc, days_active)
            return None

        if days_active < _MIN_DAYS_ACTIVE:
            return None

        # t0 MUST be read from regression_baseline trigger (Section 8.6.3)
        baseline = self._get_regression_baseline(active_arc.id)
        if baseline is None:
            return None

        t0 = baseline["avg_staleness_at_trigger"]

        metrics = self.regression_trigger._get_staleness_metrics(user_id)
        t_now = metrics["avg_staleness"]

        improvement_ratio = self._calculate_improvement_ratio(t0, t_now)

        if improvement_ratio < recovery_improvement_threshold:
            return None

        if t_now > recovery_absolute_staleness_threshold:
            return None

        return self._transition_to_redemption(
            regression_arc=active_arc,
            improvement_ratio=improvement_ratio,
            t_now=t_now,
            days_active=days_active,
        )

    # ------------------------------------------------------------------ #
    # Improvement ratio                                                   #
    # ------------------------------------------------------------------ #

    def _calculate_improvement_ratio(self, t0: float, t_now: float) -> float:
        """Calculate improvement ratio (Section 8.6.3).

        Formula: clamp((t0 - t_now) / max(t0, 1e-9), 0.0, 1.0)
        """
        ratio = (t0 - t_now) / max(t0, 1e-9)
        return max(0.0, min(1.0, ratio))

    # ------------------------------------------------------------------ #
    # Baseline retrieval                                                  #
    # ------------------------------------------------------------------ #

    def _get_regression_baseline(self, arc_id: str) -> Optional[dict]:
        """Return parsed regression_baseline trigger data for *arc_id*.

        Section 8.6.3: t0 MUST come from the regression_baseline trigger.
        Returns None if the trigger is missing or its data is unparseable.
        """
        trigger = (
            self.db.query(ArcTrigger)
            .filter(
                ArcTrigger.arc_id == arc_id,
                ArcTrigger.trigger_type == "regression_baseline",
            )
            .first()
        )

        if not trigger or not trigger.trigger_data:
            return None

        try:
            return json.loads(trigger.trigger_data)
        except (json.JSONDecodeError, TypeError):
            return None

    # ------------------------------------------------------------------ #
    # Atomic transition                                                   #
    # ------------------------------------------------------------------ #

    def _transition_to_redemption(
        self,
        regression_arc: StoryArc,
        improvement_ratio: float,
        t_now: float,
        days_active: float,
    ) -> StoryArc:
        """Atomic transition: Regression → Redemption (Section 8.6.3).

        Steps (single commit):
          1. Mark Regression as completed
          2. Create Redemption arc (active)
          3. Write recovery_detected on Redemption (with regression_arc_id + improvement_ratio)
          4. Write regression_completed on Regression
        """
        now = now_utc_fixed_ms()

        # 1. Mark Regression as completed
        regression_arc.status = "completed"
        regression_arc.completed_at = now
        regression_arc.updated_at = now

        # 2. Create Redemption arc (active)
        redemption_arc = StoryArc(
            id=str(uuid.uuid4()),
            user_id=regression_arc.user_id,
            arc_type="redemption",
            status="active",
            event_name=None,
            xp_requirement_multiplier_bp=10000,  # 1.0x normal requirements
            xp_reward_multiplier_bp=15000,        # 1.5x increased rewards
            decay_rate_multiplier_bp=10000,       # 1.0x normal decay
            started_at=now,
            duration_days=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        self.db.add(redemption_arc)
        self.db.flush()

        # 3. Write recovery_detected on Redemption
        self.lifecycle._write_trigger(
            arc_id=redemption_arc.id,
            user_id=regression_arc.user_id,
            trigger_type="recovery_detected",
            trigger_data={
                "regression_arc_id": regression_arc.id,
                "improvement_ratio": round(improvement_ratio, 4),
                "final_avg_staleness": round(t_now, 4),
                "regression_days_active": round(days_active, 2),
            },
            confidence_score=improvement_ratio,
            now=now,
        )

        # 4. Write regression_completed on Regression
        self.lifecycle._write_trigger(
            arc_id=regression_arc.id,
            user_id=regression_arc.user_id,
            trigger_type="regression_completed",
            trigger_data={
                "redemption_arc_id": redemption_arc.id,
                "improvement_ratio": round(improvement_ratio, 4),
            },
            now=now,
        )

        user = self.db.query(User).filter(User.id == regression_arc.user_id).one_or_none()
        if user is not None:
            user.active_arc_id = redemption_arc.id

        self.db.flush()
        return redemption_arc

    # ------------------------------------------------------------------ #
    # Safety valve                                                        #
    # ------------------------------------------------------------------ #

    def _apply_safety_valve(
        self, regression_arc: StoryArc, days_active: float
    ) -> None:
        """Auto-abandon regression at safety valve threshold (Section 8.6.3).

        Triggers when days_active >= regression_safety_valve_days (default 60).
        """
        self.lifecycle._abandon_arc(
            arc=regression_arc,
            now=now_utc_fixed_ms(),
            reason="auto_safety_valve",
            trigger_data={
                "days_active": round(days_active, 2),
                "threshold_days": DEFAULT_REGRESSION_SAFETY_VALVE_DAYS,
            },
        )
