"""
Regression arc trigger detection.

Implements Section 8.6.2 (Regression trigger) from architecture.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from src.db.models.skill import Skill
from src.db.models.story import StoryArc
from src.core.arc_lifecycle import ArcLifecycleService
from src.core.arc_timestamps import now_utc_fixed_ms


# Default thresholds (configurable)
DEFAULT_AVG_STALENESS_THRESHOLD: float = 0.40
DEFAULT_HIGH_STALENESS_THRESHOLD: float = 0.60
DEFAULT_HIGH_STALENESS_COUNT_THRESHOLD: int = 3


class RegressionTriggerService:
    """Detect and trigger regression arcs (Section 8.6.2)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.lifecycle = ArcLifecycleService(db)

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def check_and_trigger_regression(
        self,
        user_id: str,
        avg_staleness_threshold: float = DEFAULT_AVG_STALENESS_THRESHOLD,
        high_staleness_threshold: float = DEFAULT_HIGH_STALENESS_THRESHOLD,
        high_staleness_count_threshold: int = DEFAULT_HIGH_STALENESS_COUNT_THRESHOLD,
    ) -> Optional[StoryArc]:
        """Check regression trigger conditions and create arc if met.

        Section 8.6.2: Skill decay trigger.
        Section 8.5.3: Non-interruption policy.

        Returns:
            StoryArc if regression triggered, None otherwise.
        """
        metrics = self._get_staleness_metrics(
            user_id, high_staleness_threshold=high_staleness_threshold
        )

        avg_staleness = metrics["avg_staleness"]
        high_staleness_count = metrics["high_staleness_count"]

        # --- Trigger condition check (both conditions must be met) ---
        if avg_staleness < avg_staleness_threshold:
            return None
        if high_staleness_count < high_staleness_count_threshold:
            return None

        thresholds = {
            "avg_staleness_threshold": avg_staleness_threshold,
            "high_staleness_threshold": high_staleness_threshold,
        }

        # --- Non-interruption policy (Section 8.5.3) ---
        active_arc = self.lifecycle.get_active_arc(user_id)
        if active_arc is not None:
            if active_arc.arc_type == "event" and active_arc.event_name == "vacation_mode":
                self._write_suppressed_trigger(
                    user_id=user_id,
                    vacation_arc_id=active_arc.id,
                    metrics=metrics,
                    thresholds=thresholds,
                )
                return None
            elif active_arc.arc_type == "event":
                self._write_deferred_trigger(
                    user_id=user_id,
                    event_arc_id=active_arc.id,
                    metrics=metrics,
                    thresholds=thresholds,
                )
                return None

        # --- Create regression arc ---
        regression_arc = self.lifecycle.create_arc(
            user_id=user_id,
            arc_type="regression",
            xp_requirement_multiplier_bp=8000,   # 0.8x easier requirements
            xp_reward_multiplier_bp=10000,        # 1.0x normal rewards
            decay_rate_multiplier_bp=8000,        # 0.8x slower decay during regression
            make_active=True,
        )

        now = now_utc_fixed_ms()

        # Baseline trigger (REQUIRED — Section 8.6.2)
        self.lifecycle._write_trigger(
            arc_id=regression_arc.id,
            user_id=user_id,
            trigger_type="regression_baseline",
            trigger_data={
                "avg_staleness_at_trigger": avg_staleness,
                "eligible_skill_count": metrics["eligible_skill_count"],
                "high_staleness_count": high_staleness_count,
                "avg_staleness_threshold": avg_staleness_threshold,
                "high_staleness_threshold": high_staleness_threshold,
                "source": "skill_decay",
            },
            confidence_score=None,
            now=now,
        )

        # skill_decay trigger — confidence_score = avg_staleness
        self.lifecycle._write_trigger(
            arc_id=regression_arc.id,
            user_id=user_id,
            trigger_type="skill_decay",
            trigger_data={
                "avg_staleness": avg_staleness,
                "high_staleness_count": high_staleness_count,
            },
            confidence_score=avg_staleness,
            now=now,
        )

        self.db.flush()
        return regression_arc

    # ------------------------------------------------------------------ #
    # Metrics                                                             #
    # ------------------------------------------------------------------ #

    def _get_staleness_metrics(
        self,
        user_id: str,
        high_staleness_threshold: float = DEFAULT_HIGH_STALENESS_THRESHOLD,
    ) -> dict:
        """Calculate staleness metrics for *user_id*.

        Returns:
            {
                'avg_staleness': float,
                'high_staleness_count': int,
                'eligible_skill_count': int,
                'skills_by_staleness': list[{skill_id, staleness}]
            }
        """
        skills = (
            self.db.query(Skill)
            .filter(Skill.user_id == user_id)
            .all()
        )

        if not skills:
            return {
                "avg_staleness": 0.0,
                "high_staleness_count": 0,
                "eligible_skill_count": 0,
                "skills_by_staleness": [],
            }

        staleness_values = [s.staleness for s in skills]
        avg_staleness = sum(staleness_values) / len(staleness_values)
        high_staleness_count = sum(
            1 for v in staleness_values if v >= high_staleness_threshold
        )
        skills_by_staleness = sorted(
            [{"skill_id": s.id, "staleness": s.staleness} for s in skills],
            key=lambda x: x["staleness"],
            reverse=True,
        )

        return {
            "avg_staleness": avg_staleness,
            "high_staleness_count": high_staleness_count,
            "eligible_skill_count": len(skills),
            "skills_by_staleness": skills_by_staleness,
        }

    # ------------------------------------------------------------------ #
    # Deferred / suppressed triggers                                      #
    # ------------------------------------------------------------------ #

    def _write_deferred_trigger(
        self,
        user_id: str,
        event_arc_id: str,
        metrics: dict,
        thresholds: dict,
    ) -> None:
        """Write regression_deferred trigger on the blocking event arc.

        Section 8.5.3: Regression cannot interrupt an active non-vacation event.
        """
        now = now_utc_fixed_ms()
        self.lifecycle._write_trigger(
            arc_id=event_arc_id,
            user_id=user_id,
            trigger_type="regression_deferred",
            trigger_data={
                "avg_staleness_at_trigger": metrics["avg_staleness"],
                "eligible_skill_count": metrics["eligible_skill_count"],
                "high_staleness_count": metrics["high_staleness_count"],
                "avg_staleness_threshold": thresholds["avg_staleness_threshold"],
                "high_staleness_threshold": thresholds["high_staleness_threshold"],
                "source": "skill_decay",
                "deferred_at_utc": now,
            },
            now=now,
        )
        self.db.flush()

    def _write_suppressed_trigger(
        self,
        user_id: str,
        vacation_arc_id: str,
        metrics: dict,
        thresholds: dict,
    ) -> None:
        """Write regression_suppressed trigger on the vacation arc.

        Section 8.5.3: Regression is suppressed during vacation.
        """
        now = now_utc_fixed_ms()
        self.lifecycle._write_trigger(
            arc_id=vacation_arc_id,
            user_id=user_id,
            trigger_type="regression_suppressed",
            trigger_data={
                "avg_staleness_at_trigger": metrics["avg_staleness"],
                "eligible_skill_count": metrics["eligible_skill_count"],
                "high_staleness_count": metrics["high_staleness_count"],
                "avg_staleness_threshold": thresholds["avg_staleness_threshold"],
                "high_staleness_threshold": thresholds["high_staleness_threshold"],
                "source": "skill_decay",
                "suppressed_at_utc": now,
            },
            now=now,
        )
        self.db.flush()
