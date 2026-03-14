"""
Story arc lifecycle management.

Implements Section 8.5 (Lifecycle and State Machine) from architecture.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from src.db.models.story import ArcTrigger, StoryArc
from src.db.models.user import User
from src.core.arc_timestamps import now_utc_fixed_ms, parse_fixed_ms_timestamp


class ArcLifecycleService:
    """Manage story arc lifecycle and state transitions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Query                                                               #
    # ------------------------------------------------------------------ #

    def get_active_arc(self, user_id: str) -> Optional[StoryArc]:
        """Return the active arc for *user_id*, or None (Section 8.9)."""
        return (
            self.db.query(StoryArc)
            .filter(StoryArc.user_id == user_id, StoryArc.status == "active")
            .order_by(StoryArc.started_at.desc(), StoryArc.updated_at.desc(), StoryArc.id.desc())
            .first()
        )

    def reconcile_active_arc_cache(self, user_id: str) -> Optional[StoryArc]:
        """Repair ``users.active_arc_id`` from authoritative arc rows."""
        active_arc = self.get_active_arc(user_id)
        self._set_active_arc_cache(user_id, active_arc.id if active_arc else None)
        self.db.flush()
        return active_arc

    def _set_active_arc_cache(self, user_id: str, arc_id: str | None) -> None:
        """Keep ``users.active_arc_id`` aligned with the authoritative arc row."""
        user = self.db.query(User).filter(User.id == user_id).one_or_none()
        if user is not None:
            user.active_arc_id = arc_id

    def _clear_active_arc_cache_if_matches(self, user_id: str, arc_id: str) -> None:
        user = self.db.query(User).filter(User.id == user_id).one_or_none()
        if user is not None and user.active_arc_id == arc_id:
            user.active_arc_id = None

    # ------------------------------------------------------------------ #
    # Creation                                                            #
    # ------------------------------------------------------------------ #

    def create_arc(
        self,
        user_id: str,
        arc_type: str,
        event_name: Optional[str] = None,
        theme_ids: Optional[List[str]] = None,
        duration_days: Optional[float] = None,
        xp_requirement_multiplier_bp: int = 10000,
        xp_reward_multiplier_bp: int = 10000,
        decay_rate_multiplier_bp: int = 10000,
        make_active: bool = True,
    ) -> StoryArc:
        """Create a new story arc.

        If *make_active* is True and an active arc already exists the old arc
        is replaced atomically (Section 8.5.2):

        * vacation-mode event arcs → pause the existing arc
        * all other arc types      → abandon the existing arc
        """
        now = now_utc_fixed_ms()

        if arc_type == "event" and not event_name:
            raise ValueError("Event arcs require event_name")
        if arc_type != "event" and event_name:
            raise ValueError(f"{arc_type} arcs must not have event_name")

        if make_active:
            existing = self.get_active_arc(user_id)
            if existing:
                if arc_type == "event" and event_name == "vacation_mode":
                    self._pause_arc(existing, now)
                else:
                    self._abandon_arc(existing, now, reason="replaced_by_new_arc")

        arc = StoryArc(
            id=str(uuid.uuid4()),
            user_id=user_id,
            arc_type=arc_type,
            status="active" if make_active else "paused",
            event_name=event_name,
            xp_requirement_multiplier_bp=xp_requirement_multiplier_bp,
            xp_reward_multiplier_bp=xp_reward_multiplier_bp,
            decay_rate_multiplier_bp=decay_rate_multiplier_bp,
            started_at=now,
            duration_days=duration_days,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )

        if theme_ids:
            arc.theme_ids_list = theme_ids

        self.db.add(arc)
        self.db.flush()
        self._set_active_arc_cache(user_id, arc.id if make_active else None)
        self.db.flush()

        return arc

    # ------------------------------------------------------------------ #
    # Terminal transitions                                                #
    # ------------------------------------------------------------------ #

    def complete_arc(
        self,
        arc: StoryArc,
        trigger_type: str = "auto_expiry",
        trigger_data: Optional[dict] = None,
    ) -> StoryArc:
        """Mark *arc* as completed (terminal — Section 8.5.1)."""
        now = now_utc_fixed_ms()

        arc.status = "completed"
        arc.completed_at = now
        arc.updated_at = now

        self._write_trigger(
            arc_id=arc.id,
            user_id=arc.user_id,
            trigger_type=trigger_type,
            trigger_data=trigger_data,
            now=now,
        )

        self._clear_active_arc_cache_if_matches(arc.user_id, arc.id)
        self.db.flush()
        return arc

    def abandon_arc(
        self,
        arc: StoryArc,
        reason: str = "user_abandon",
        trigger_data: Optional[dict] = None,
    ) -> StoryArc:
        """Mark *arc* as abandoned (terminal — Section 8.5.1)."""
        return self._abandon_arc(arc, now_utc_fixed_ms(), reason, trigger_data)

    def _abandon_arc(
        self,
        arc: StoryArc,
        now: str,
        reason: str = "user_abandon",
        trigger_data: Optional[dict] = None,
    ) -> StoryArc:
        arc.status = "abandoned"
        arc.completed_at = now
        arc.updated_at = now

        self._write_trigger(
            arc_id=arc.id,
            user_id=arc.user_id,
            trigger_type=reason,
            trigger_data=trigger_data,
            now=now,
        )

        self._clear_active_arc_cache_if_matches(arc.user_id, arc.id)
        self.db.flush()
        return arc

    # ------------------------------------------------------------------ #
    # Pause / resume                                                      #
    # ------------------------------------------------------------------ #

    def pause_arc(self, arc: StoryArc) -> StoryArc:
        """Pause *arc* (vacation mode — Section 8.5.4)."""
        return self._pause_arc(arc, now_utc_fixed_ms())

    def _pause_arc(self, arc: StoryArc, now: str) -> StoryArc:
        arc.status = "paused"
        arc.updated_at = now

        self._write_trigger(
            arc_id=arc.id,
            user_id=arc.user_id,
            trigger_type="vacation_pause",
            now=now,
        )

        self._clear_active_arc_cache_if_matches(arc.user_id, arc.id)
        self.db.flush()
        return arc

    def resume_arc(self, arc: StoryArc) -> StoryArc:
        """Resume a paused arc.

        CRITICAL: ``started_at`` is never modified on resume (Section 8.5.4).
        """
        now = now_utc_fixed_ms()

        arc.status = "active"
        arc.updated_at = now
        # started_at is intentionally left unchanged

        self._write_trigger(
            arc_id=arc.id,
            user_id=arc.user_id,
            trigger_type="vacation_resume",
            now=now,
        )

        self._set_active_arc_cache(arc.user_id, arc.id)
        self.db.flush()
        return arc

    # ------------------------------------------------------------------ #
    # days_active calculation                                             #
    # ------------------------------------------------------------------ #

    def calculate_days_active(
        self,
        arc: StoryArc,
        now_utc: Optional[datetime] = None,
    ) -> float:
        """Return days the arc has actually been active (Section 8.2.4).

        Total elapsed time minus all paused intervals.

        Args:
            arc:     Story arc to evaluate.
            now_utc: Reference instant (timezone-aware UTC); defaults to now.

        Returns:
            days_active as a non-negative float.
        """
        now_utc = now_utc or datetime.now(timezone.utc)

        started_dt = parse_fixed_ms_timestamp(arc.started_at)
        elapsed_ms = (now_utc - started_dt).total_seconds() * 1000

        pause_intervals = self._get_pause_intervals(arc.id, now_utc)
        total_paused_ms = sum(iv["duration_ms"] for iv in pause_intervals)

        active_ms = elapsed_ms - total_paused_ms
        return max(0.0, active_ms / (24 * 60 * 60 * 1000))

    def _get_pause_intervals(
        self, arc_id: str, now_utc: Optional[datetime] = None
    ) -> List[dict]:
        """Return list of ``{paused_at_ms, resumed_at_ms, duration_ms}`` dicts.

        An open pause (arc still paused) is closed against *now_utc*.
        """
        now_utc = now_utc or datetime.now(timezone.utc)

        triggers = (
            self.db.query(ArcTrigger)
            .filter(
                ArcTrigger.arc_id == arc_id,
                ArcTrigger.trigger_type.in_(["vacation_pause", "vacation_resume"]),
            )
            .order_by(ArcTrigger.triggered_at)
            .all()
        )

        intervals: List[dict] = []
        paused_at_ms: Optional[int] = None

        for trigger in triggers:
            trigger_dt = parse_fixed_ms_timestamp(trigger.triggered_at)
            trigger_ms = int(trigger_dt.timestamp() * 1000)

            if trigger.trigger_type == "vacation_pause":
                paused_at_ms = trigger_ms
            elif trigger.trigger_type == "vacation_resume" and paused_at_ms is not None:
                duration_ms = trigger_ms - paused_at_ms
                intervals.append(
                    {
                        "paused_at_ms": paused_at_ms,
                        "resumed_at_ms": trigger_ms,
                        "duration_ms": duration_ms,
                    }
                )
                paused_at_ms = None

        # Open pause — close against now
        if paused_at_ms is not None:
            now_ms = int(now_utc.timestamp() * 1000)
            intervals.append(
                {
                    "paused_at_ms": paused_at_ms,
                    "resumed_at_ms": now_ms,
                    "duration_ms": now_ms - paused_at_ms,
                }
            )

        return intervals

    # ------------------------------------------------------------------ #
    # Trigger helpers                                                     #
    # ------------------------------------------------------------------ #

    def _write_trigger(
        self,
        arc_id: str,
        user_id: str,
        trigger_type: str,
        trigger_data: Optional[dict] = None,
        confidence_score: Optional[float] = None,
        now: Optional[str] = None,
    ) -> ArcTrigger:
        """Append an immutable audit trigger (Section 8.2.2).

        Does NOT commit — callers are responsible for committing.
        """
        now = now or now_utc_fixed_ms()

        trigger = ArcTrigger(
            id=str(uuid.uuid4()),
            user_id=user_id,
            arc_id=arc_id,
            trigger_type=trigger_type,
            confidence_score=confidence_score,
            trigger_data=(
                json.dumps(trigger_data, separators=(",", ":"))
                if trigger_data is not None
                else None
            ),
            triggered_at=now,
        )

        self.db.add(trigger)
        return trigger
