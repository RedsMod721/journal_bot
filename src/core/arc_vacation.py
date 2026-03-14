"""
Vacation mode management.

Implements Section 8.3.5 (Vacation Mode) and 8.5.4 (Pause/Resume) from architecture.

Trigger anatomy
---------------
When vacation is activated two sets of triggers are written:

  1. ``vacation_pause`` on the **paused arc** (written by lifecycle._pause_arc)
     — picked up by calculate_days_active to subtract paused duration.

  2. ``vacation_pause`` on the **vacation arc** (written here) with
     ``trigger_data={'paused_arc_id': ..., 'paused_arc_type': ...}``
     — used by _find_paused_arc_for_vacation so end_vacation can locate the
       arc to resume without a full table scan.

When vacation ends:

  3. ``user_end`` on the vacation arc (written by complete_arc).

  4. ``vacation_resume`` on the **resumed arc** (written by lifecycle.resume_arc)
     — closes the open pause interval so calculate_days_active is accurate.
"""

from __future__ import annotations

import json
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from src.core.arc_lifecycle import ArcLifecycleService
from src.db.models.story import ArcTrigger, StoryArc


class VacationModeService:
    """Manage vacation mode activation and ending."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.lifecycle = ArcLifecycleService(db)

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def activate_vacation(
        self,
        user_id: str,
        duration_days: Optional[float] = None,
    ) -> Tuple[StoryArc, Optional[StoryArc]]:
        """Activate vacation mode.

        Section 8.3.5: vacation becomes the active arc; current arc is paused.

        Steps:
            1. Get current active arc (captured before create_arc changes it).
            2. Guard: return early if already in vacation mode.
            3. create_arc with event_name='vacation_mode' — internally calls
               _pause_arc on the existing arc (writes vacation_pause trigger on
               the paused arc and sets its status='paused').
            4. Write vacation_pause trigger on the vacation arc recording which
               arc was paused (for later retrieval by end_vacation).

        Args:
            user_id:      Owner user UUID.
            duration_days: Optional planned vacation length.

        Returns:
            ``(vacation_arc, paused_arc)`` — paused_arc is None if no arc was
            active before vacation started.
        """
        current_active = self.lifecycle.get_active_arc(user_id)

        if current_active and current_active.event_name == "vacation_mode":
            # Already in vacation — idempotent, return as-is.
            return current_active, None

        # create_arc handles pausing the existing arc when event_name=='vacation_mode'.
        vacation_arc = self.lifecycle.create_arc(
            user_id=user_id,
            arc_type="event",
            event_name="vacation_mode",
            duration_days=duration_days,
            xp_requirement_multiplier_bp=10000,
            xp_reward_multiplier_bp=10000,
            decay_rate_multiplier_bp=0,  # Section 8.3.5: no decay during vacation
            make_active=True,
        )

        paused_arc: Optional[StoryArc] = None
        if current_active:
            # Refresh to pick up status='paused' written by create_arc._pause_arc.
            self.db.refresh(current_active)
            paused_arc = current_active

            # Write a vacation_pause trigger ON THE VACATION ARC with paused_arc_id
            # so end_vacation can find the arc to resume without a full table scan.
            self.lifecycle._write_trigger(
                arc_id=vacation_arc.id,
                user_id=user_id,
                trigger_type="vacation_pause",
                trigger_data={
                    "paused_arc_id": paused_arc.id,
                    "paused_arc_type": paused_arc.arc_type,
                },
            )
            self.db.flush()

        return vacation_arc, paused_arc

    def end_vacation(
        self,
        user_id: str,
    ) -> Tuple[StoryArc, Optional[StoryArc]]:
        """End vacation mode and resume the previously paused arc.

        Section 8.5.4: started_at of the resumed arc is NEVER modified.

        Steps:
            1. Verify an active vacation arc exists.
            2. Find the arc paused when vacation started.
            3. Complete the vacation arc.
            4. Resume the paused arc (lifecycle.resume_arc writes vacation_resume
               trigger on the resumed arc, closing its pause interval for
               calculate_days_active).

        Args:
            user_id: Owner user UUID.

        Returns:
            ``(vacation_arc, resumed_arc)`` — resumed_arc is None if no arc was
            paused when vacation started.

        Raises:
            ValueError: If no active vacation arc exists for this user.
        """
        vacation_arc = self.lifecycle.get_active_arc(user_id)

        if not vacation_arc or vacation_arc.event_name != "vacation_mode":
            raise ValueError(f"No active vacation mode to end for user {user_id!r}")

        paused_arc = self._find_paused_arc_for_vacation(vacation_arc.id)

        # Mark vacation as completed (writes user_end trigger).
        vacation_arc = self.lifecycle.complete_arc(
            arc=vacation_arc,
            trigger_type="user_end",
            trigger_data={"reason": "vacation_ended"},
        )

        resumed_arc: Optional[StoryArc] = None
        if paused_arc:
            try:
                # resume_arc sets status='active', updates updated_at, and writes
                # vacation_resume trigger — started_at is intentionally left alone.
                resumed_arc = self.lifecycle.resume_arc(paused_arc)
            except Exception as exc:  # noqa: BLE001
                self.lifecycle._write_trigger(
                    arc_id=vacation_arc.id,
                    user_id=user_id,
                    trigger_type="vacation_resume_failed",
                    trigger_data={
                        "paused_arc_id": paused_arc.id,
                        "error": str(exc),
                    },
                )
                self.db.flush()

        return vacation_arc, resumed_arc

    def get_vacation_status(self, user_id: str) -> dict:
        """Return a snapshot of current vacation mode state.

        Returns:
            ``{
                'in_vacation': bool,
                'vacation_arc': StoryArc | None,
                'paused_arc': StoryArc | None,
                'days_active': float | None,
            }``
        """
        active_arc = self.lifecycle.get_active_arc(user_id)

        if not active_arc or active_arc.event_name != "vacation_mode":
            return {
                "in_vacation": False,
                "vacation_arc": None,
                "paused_arc": None,
                "days_active": None,
            }

        paused_arc = self._find_paused_arc_for_vacation(active_arc.id)
        days_active = self.lifecycle.calculate_days_active(active_arc)

        return {
            "in_vacation": True,
            "vacation_arc": active_arc,
            "paused_arc": paused_arc,
            "days_active": days_active,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _find_paused_arc_for_vacation(self, vacation_arc_id: str) -> Optional[StoryArc]:
        """Return the arc that was paused when this vacation started, or None.

        Looks for a vacation_pause trigger written on the vacation arc itself
        (distinct from the trigger written on the paused arc by _pause_arc)
        whose trigger_data contains ``paused_arc_id``.
        """
        trigger = (
            self.db.query(ArcTrigger)
            .filter(
                ArcTrigger.arc_id == vacation_arc_id,
                ArcTrigger.trigger_type == "vacation_pause",
            )
            .first()
        )

        if not trigger or not trigger.trigger_data:
            return None

        try:
            data = json.loads(trigger.trigger_data)
            paused_arc_id: Optional[str] = data.get("paused_arc_id")
        except (ValueError, TypeError):
            return None

        if not paused_arc_id:
            return None

        return (
            self.db.query(StoryArc)
            .filter(
                StoryArc.id == paused_arc_id,
                StoryArc.status == "paused",
            )
            .first()
        )
