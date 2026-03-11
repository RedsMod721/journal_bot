"""
Forgiveness decay calculation service.

Implements Section 4.3 (Core Forgiveness Mechanics) from architecture.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from typing import Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from src.core.forgiveness_config_service import ForgivenessConfigService
from src.db.models.forgiveness import DecaySnapshot
from src.db.models.insight import Insight
from src.db.models.skill import Skill
from src.db.models.story import StoryArc
from src.db.models.user import User

_FALLBACK_TZ = "UTC"


class ForgivenessDecayService:
    """Service for calculating and applying forgiveness decay."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.config_service = ForgivenessConfigService(db)

    # ------------------------------------------------------------------
    # Skill staleness
    # ------------------------------------------------------------------

    def decay_skills(self, user_id: str, now_utc: datetime) -> Dict[str, object]:
        """
        Calculate and apply skill staleness decay for a user.

        Returns aggregate metrics describing what changed.
        """
        config = self.config_service.resolve_effective_config(user_id, now_utc)
        arc_decay_multiplier = self._get_active_arc_decay_multiplier(user_id)

        skills = self.db.query(Skill).filter(Skill.user_id == user_id).all()

        metrics: Dict[str, object] = {
            "skills_processed": 0,
            "skills_decayed": 0,
            "critical_skills": 0,
            "stale_skills": 0,
            "avg_staleness": 0.0,
        }

        total_staleness = 0.0

        for skill in skills:
            if skill.decay_paused:
                continue

            old_staleness = skill.staleness
            new_staleness = self._calculate_skill_staleness(
                skill=skill,
                now_utc=now_utc,
                decay_rate=config.skill_decay_rate * arc_decay_multiplier,
                grace_days=config.skill_grace_days,
            )

            # Max rule — staleness can only increase
            skill.staleness = max(skill.staleness, new_staleness)

            metrics["skills_processed"] += 1
            total_staleness += skill.staleness

            if skill.staleness > old_staleness:
                metrics["skills_decayed"] += 1

            if skill.staleness >= config.critical_threshold:
                metrics["critical_skills"] += 1
            elif skill.staleness >= config.critical_threshold - 0.10:
                metrics["stale_skills"] += 1

        if metrics["skills_processed"] > 0:
            metrics["avg_staleness"] = total_staleness / metrics["skills_processed"]

        self.db.commit()
        return metrics

    def _calculate_skill_staleness(
        self,
        skill: Skill,
        now_utc: datetime,
        decay_rate: float,
        grace_days: int,
    ) -> float:
        """
        Calculate target staleness for a skill.

        Formula (Section 4.3.1):
            days_inactive  = seconds(now - last_activity_at) / 86400
            effective_days = max(0, days_inactive - grace_days)
            staleness      = 1 - exp(-decay_rate * effective_days)
        """
        if not skill.last_activity_at:
            return 0.0

        days_inactive = self._fractional_days_between(skill.last_activity_at, now_utc)
        effective_days = max(0.0, days_inactive - grace_days)
        staleness = 1.0 - math.exp(-decay_rate * effective_days)
        return max(0.0, min(1.0, staleness))

    # ------------------------------------------------------------------
    # Insight strength
    # ------------------------------------------------------------------

    def decay_insights(self, user_id: str, now_utc: datetime) -> Dict[str, object]:
        """
        Calculate and apply insight strength decay for a user.

        Returns aggregate metrics describing what changed.
        """
        config = self.config_service.resolve_effective_config(user_id, now_utc)
        arc_decay_multiplier = self._get_active_arc_decay_multiplier(user_id)

        insights = self.db.query(Insight).filter(Insight.user_id == user_id).all()

        metrics: Dict[str, object] = {
            "insights_processed": 0,
            "insights_decayed": 0,
            "weak_insights": 0,
            "avg_strength": 1.0,
        }

        total_strength = 0.0

        for insight in insights:
            old_strength = insight.strength
            new_strength = self._calculate_insight_strength(
                insight=insight,
                now_utc=now_utc,
                decay_rate=config.insight_decay_rate * arc_decay_multiplier,
                grace_days=config.insight_grace_days,
            )

            # Min rule — strength can only decrease
            insight.strength = min(insight.strength, new_strength)

            metrics["insights_processed"] += 1
            total_strength += insight.strength

            if insight.strength < old_strength:
                metrics["insights_decayed"] += 1

            if insight.strength < 0.5:
                metrics["weak_insights"] += 1

        if metrics["insights_processed"] > 0:
            metrics["avg_strength"] = total_strength / metrics["insights_processed"]

        self.db.commit()
        return metrics

    def _calculate_insight_strength(
        self,
        insight: Insight,
        now_utc: datetime,
        decay_rate: float,
        grace_days: int,
    ) -> float:
        """
        Calculate target strength for an insight.

        Formula (Section 4.3.2):
            days_since     = seconds(now - last_reinforced_at) / 86400
            effective_days = max(0, days_since - grace_days)
            strength       = exp(-decay_rate * effective_days)

        Falls back to ``created_at`` when ``last_reinforced_at`` is unset.
        """
        last_reinforced = insight.last_reinforced_at or insight.created_at
        if not last_reinforced:
            return 1.0

        days_since = self._fractional_days_between(last_reinforced, now_utc)
        effective_days = max(0.0, days_since - grace_days)
        strength = math.exp(-decay_rate * effective_days)
        return max(0.0, min(1.0, strength))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fractional_days_between(
        timestamp_a: datetime,
        timestamp_b: datetime,
    ) -> float:
        """
        Return (timestamp_b - timestamp_a) in fractional days, always >= 0.

        Naive datetimes are assumed to be UTC.
        """
        if timestamp_a.tzinfo is None:
            timestamp_a = timestamp_a.replace(tzinfo=timezone.utc)
        if timestamp_b.tzinfo is None:
            timestamp_b = timestamp_b.replace(tzinfo=timezone.utc)

        delta = timestamp_b - timestamp_a
        return max(0.0, delta.total_seconds()) / 86400.0

    # ------------------------------------------------------------------
    # Reset helpers (called by pipeline steps on activity / reinforcement)
    # ------------------------------------------------------------------

    def reset_skill_staleness(self, skill: Skill, now_utc: datetime) -> None:
        """Compatibility wrapper: apply normal reinforcement and record activity."""
        skill.last_activity_at = now_utc
        if not skill.decay_paused:
            skill.staleness = max(0.0, min(1.0, skill.staleness * 0.50))

    def reinforce_skill(
        self,
        skill: Skill,
        now_utc: datetime,
        *,
        is_primary: bool = False,
        xp_amount: int = 0,
    ) -> None:
        """Reduce staleness according to the architecture reinforcement rules."""
        skill.last_activity_at = now_utc
        if skill.decay_paused:
            return
        multiplier = 0.25 if is_primary and xp_amount >= 480 else 0.50
        skill.staleness = max(0.0, min(1.0, skill.staleness * multiplier))

    def reinforce_insight(self, insight: Insight, now_utc: datetime) -> None:
        """Increment insight strength and record reinforcement timestamp."""
        insight.last_reinforced_at = now_utc
        insight.strength = max(0.0, min(1.0, insight.strength + 0.20))

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def create_decay_snapshot(
        self,
        user_id: str,
        snapshot_date: date,
        now_utc: datetime,
    ) -> DecaySnapshot:
        """
        Upsert a daily decay snapshot for a user.

        Aggregates current staleness / strength values into the snapshot row.
        Idempotent: updates an existing row if one already exists for the date.

        Insight "staleness" is stored as (1 - strength) so all maps share the
        same semantics (0.0 = fresh, 1.0 = fully decayed).
        """
        skills = (
            self.db.query(Skill)
            .filter(
                Skill.user_id == user_id,
                Skill.decay_paused.is_(False),
                ((Skill.xp > 0) | (Skill.level > 1) | Skill.last_activity_at.is_not(None)),
            )
            .all()
        )
        insights = (
            self.db.query(Insight)
            .filter(Insight.user_id == user_id, Insight.status == "active")
            .all()
        )

        config = self.config_service.resolve_effective_config(user_id, now_utc)
        near_critical_threshold = config.critical_threshold - 0.10

        avg_skill_staleness = (
            sum(s.staleness for s in skills) / len(skills) if skills else 0.0
        )
        # insight staleness = 1 - strength (higher = more decayed)
        avg_insight_staleness = (
            sum(1.0 - i.strength for i in insights) / len(insights)
            if insights
            else 0.0
        )
        skills_near_critical = sum(
            1 for s in skills if s.staleness >= near_critical_threshold
        )

        skill_staleness_map = json.dumps({s.id: round(s.staleness, 4) for s in skills})
        insight_staleness_map = json.dumps(
            {i.id: round(1.0 - i.strength, 4) for i in insights}
        )

        date_str = snapshot_date.isoformat()

        existing = (
            self.db.query(DecaySnapshot)
            .filter(
                DecaySnapshot.user_id == user_id,
                DecaySnapshot.snapshot_date == date_str,
            )
            .first()
        )

        if existing:
            existing.average_skill_staleness = avg_skill_staleness
            existing.average_insight_staleness = avg_insight_staleness
            existing.skills_near_critical = skills_near_critical
            existing.skill_staleness_map = skill_staleness_map
            existing.insight_staleness_map = insight_staleness_map
            snapshot = existing
        else:
            snapshot = DecaySnapshot(
                user_id=user_id,
                snapshot_date=date_str,
                average_skill_staleness=avg_skill_staleness,
                average_insight_staleness=avg_insight_staleness,
                skills_near_critical=skills_near_critical,
                skill_staleness_map=skill_staleness_map,
                insight_staleness_map=insight_staleness_map,
            )
            self.db.add(snapshot)

        self.db.commit()
        return snapshot

    def resolve_snapshot_date(self, user_id: str, now_utc: datetime) -> date:
        user = self.db.query(User).filter(User.id == user_id).one_or_none()
        if user is None:
            raise ValueError(f"User not found: {user_id}")
        normalized = now_utc if now_utc.tzinfo is not None else now_utc.replace(tzinfo=timezone.utc)
        return normalized.astimezone(self._user_tz(user.timezone)).date()

    def _get_active_arc_decay_multiplier(self, user_id: str) -> float:
        user = self.db.query(User).filter(User.id == user_id).one_or_none()
        if user is None:
            return 1.0

        arc: StoryArc | None = None
        if user.active_arc_id:
            arc = (
                self.db.query(StoryArc)
                .filter(
                    StoryArc.user_id == user_id,
                    StoryArc.id == user.active_arc_id,
                    StoryArc.status == "active",
                )
                .one_or_none()
            )
            if arc is None:
                user.active_arc_id = None
                self.db.flush()

        if arc is None:
            arc = (
                self.db.query(StoryArc)
                .filter(
                    StoryArc.user_id == user_id,
                    StoryArc.status == "active",
                )
                .order_by(StoryArc.started_at.desc(), StoryArc.id.desc())
                .first()
            )
            if arc is not None and user.active_arc_id != arc.id:
                user.active_arc_id = arc.id
                self.db.flush()

        if arc is None:
            return 1.0
        return max(0.0, min(1.0, float(arc.decay_rate_multiplier)))

    @staticmethod
    def _user_tz(tz_name: str | None) -> ZoneInfo:
        try:
            return ZoneInfo(tz_name or _FALLBACK_TZ)
        except (ZoneInfoNotFoundError, KeyError):
            return ZoneInfo(_FALLBACK_TZ)
