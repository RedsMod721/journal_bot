"""Balance system diminishing returns helpers.

The canonical multiplier is shared with ``src.ai.steps.strategy``:

    diminishing_multiplier = max(0.75, 1.0 - 0.05 * max(0, streak - 2))

The API/service layer wraps the persisted ``strategy_streaks_json`` state so
read endpoints and standalone callers see the same behavior as the pipeline.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Dict

from sqlalchemy.orm import Session

from src.ai.steps.strategy import STRATEGY_KEYS, diminishing_multiplier_from_streaks
from src.db.models.strategy import StrategyTracking


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class DiminishingReturnsService:
    """Track strategy streaks and expose the canonical diminishing multiplier.

    All public methods operate on the ``StrategyTracking`` row owned by the
    given ``user_id``.  The caller is responsible for committing the session;
    this class calls ``db.flush()`` to propagate mutations within the current
    transaction (matching the convention used in ``VarietyService``).

    Example::

        svc = DiminishingReturnsService(db)
        svc.update_strategy_streaks(
            user_id=user_id,
            strategies_today=["study", "grind"],
            today_local=date.today(),
            tracking=tracking,
        )
        penalized_xp = svc.apply_diminishing_returns_to_xp(
            base_xp=100,
            strategy="study",
            user_id=user_id,
        )
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Streak management
    # ------------------------------------------------------------------

    def update_strategy_streaks(
        self,
        *,
        user_id: str,
        strategies_today: list[str],
        today_local: date,
        tracking: StrategyTracking,
    ) -> None:
        """Update streak counts for *strategies_today*.

        For each strategy in *strategies_today*:
        - ``last_day == today_local``      → already recorded; no change (idempotent).
        - ``last_day == yesterday_local``  → consecutive day; increment count.
        - any other ``last_day`` (or new)  → reset count to 1.

        Strategies *not* in *strategies_today* are left untouched so their
        historical count is preserved for display/audit purposes.

        Args:
            user_id:          Owning user UUID (unused directly; kept for
                              call-site symmetry with other services).
            strategies_today: Short strategy keys credited for today's entry
                              (e.g. ``["study", "grind"]``).
            today_local:      User-local date (UTC proxy when tz unknown).
            tracking:         The ``StrategyTracking`` ORM row to mutate
                              in-place.
        """
        if not strategies_today:
            return

        try:
            streaks: dict[str, dict[str, object]] = json.loads(
                tracking.strategy_streaks_json or "{}"
            )
        except (json.JSONDecodeError, TypeError):
            streaks = {}

        today_iso = today_local.isoformat()
        yesterday_iso = (today_local - timedelta(days=1)).isoformat()

        for sk in strategies_today:
            entry = streaks.get(sk) or {}
            last_day = entry.get("last_day")

            if last_day == today_iso:
                # Already credited this calendar day — idempotent, skip.
                continue

            if last_day == yesterday_iso:
                # Consecutive day: extend the streak.
                count = int(entry.get("count") or 0) + 1
            else:
                # Gap or brand-new strategy: start fresh.
                count = 1

            streaks[sk] = {"count": count, "last_day": today_iso}

        tracking.strategy_streaks_json = json.dumps(
            streaks, separators=(",", ":"), sort_keys=True
        )
        self.db.flush()

    # ------------------------------------------------------------------
    # Penalty calculation
    # ------------------------------------------------------------------

    def get_strategy_penalty(
        self,
        strategy: str,
        tracking: StrategyTracking,
    ) -> float:
        """Return the XP multiplier for *strategy* using yesterday-local streak state.

        Args:
            strategy: Short strategy key (e.g. ``"study"``).
            tracking: The ``StrategyTracking`` ORM row for the user.

        Returns:
            Float multiplier in [0.75, 1.00].
        """
        try:
            streaks: dict[str, dict[str, object]] = json.loads(
                tracking.strategy_streaks_json or "{}"
            )
        except (json.JSONDecodeError, TypeError):
            streaks = {}

        entry = streaks.get(strategy) or {}
        last_day_raw = entry.get("last_day")
        if not isinstance(last_day_raw, str):
            return 1.0

        try:
            yesterday_local = date.fromisoformat(last_day_raw)
        except ValueError:
            return 1.0

        return diminishing_multiplier_from_streaks(
            [strategy],
            tracking.strategy_streaks_json or "{}",
            yesterday_local,
        )

    def get_all_strategy_penalties(self, user_id: str) -> Dict[str, float]:
        """Return penalty multipliers for all six canonical strategies.

        Queries the DB for the ``StrategyTracking`` row owned by *user_id*.

        Args:
            user_id: Owning user UUID.

        Returns:
            ``{strategy_key: multiplier}`` for every key in ``STRATEGY_KEYS``.
            Returns an empty dict if no tracking row exists for this user.
        """
        tracking = (
            self.db.query(StrategyTracking)
            .filter(StrategyTracking.user_id == user_id)
            .one_or_none()
        )
        if tracking is None:
            return {}

        return {sk: self.get_strategy_penalty(sk, tracking) for sk in STRATEGY_KEYS}

    # ------------------------------------------------------------------
    # XP application
    # ------------------------------------------------------------------

    def apply_diminishing_returns_to_xp(
        self,
        base_xp: int,
        strategy: str,
        user_id: str,
    ) -> int:
        """Apply the diminishing-returns penalty to *base_xp* for *strategy*.

        Looks up the ``StrategyTracking`` row for *user_id*, determines the
        current consecutive-day count for *strategy*, and multiplies *base_xp*
        by the appropriate penalty tier.

        Args:
            base_xp:   XP amount before penalty (integer).
            strategy:  Short strategy key (e.g. ``"grind"``).
            user_id:   Owning user UUID.

        Returns:
            ``int(base_xp × penalty_multiplier)``.  Returns *base_xp*
            unchanged if no ``StrategyTracking`` row exists.
        """
        tracking = (
            self.db.query(StrategyTracking)
            .filter(StrategyTracking.user_id == user_id)
            .one_or_none()
        )
        if tracking is None:
            return base_xp

        multiplier = self.get_strategy_penalty(strategy, tracking)
        return int(base_xp * multiplier)
