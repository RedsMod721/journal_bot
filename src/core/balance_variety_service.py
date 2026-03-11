"""Balance system variety score and bonus calculation.

Implements Section 5.3 (Variety Score) and 5.3.1–5.3.2 (Variety Bonus) from
architecture.  Thin service wrapper around the pure functions in
``src.ai.steps.variety``; use this class when you need variety metrics outside
the AI pipeline (e.g. backfill scripts, API endpoints, standalone tests).

Formula summary (architecture §5.3.1–5.3.2, project override):
    variety_score         = H / log2(6)         — float 0.0 → 1.0
    variety_bonus_pct     = score² × 0.30       — float 0.0 → 0.30 (stored fraction)
    variety_multiplier_bp = 10 000 + int(bonus_pct × 10 000)  — int 10 000 → 13 000

The ``variety_bonus_pct`` column is stored as a *fraction*, NOT a percentage
(e.g. 0.30 means 30 %, not 30). The DB constraint still allows ``0.60`` so a
future Harvest Festival arc can double the effective bonus without a schema
change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from src.ai.steps.variety import STRATEGY_KEYS, _STRATEGY_COUNT_COLUMNS, calculate_variety_score
from src.db.models.strategy import StrategyTracking


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class VarietyService:
    """Service for calculating variety score and bonus."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Core calculations
    # ------------------------------------------------------------------

    def calculate_variety_score(self, strategy_counts: Dict[str, int]) -> float:
        """Calculate variety score using Shannon entropy.

        Delegates to the canonical implementation in ``src.ai.steps.variety``.

        Args:
            strategy_counts: Mapping of strategy key (``social``, ``study``,
                ``mundane``, ``troll``, ``grind``, ``harmony``) to cumulative
                usage count.  Missing keys are treated as count=0.

        Returns:
            Float in [0.0, 1.0].  0.0 = all activity in one strategy;
            1.0 = perfectly even distribution across all six.
        """
        return calculate_variety_score(strategy_counts)

    def calculate_variety_bonus_pct(self, variety_score: float) -> float:
        """Calculate variety bonus as a stored fraction using the quadratic formula.

        Formula (architecture §5.3.2):
            variety_bonus_pct = variety_score² × 0.30

        Examples:
            score 0.0 → 0.00 (0 % bonus)
            score 0.5 → 0.075 (7.5 % bonus)
            score 1.0 → 0.30 (30 % bonus)

        Args:
            variety_score: Normalised entropy in [0.0, 1.0].

        Returns:
            Bonus fraction in [0.0, 0.30]. Stored directly in
            ``StrategyTracking.variety_bonus_pct``.
        """
        return (variety_score ** 2) * 0.30

    def calculate_variety_multiplier_bp(self, variety_bonus_pct: float) -> int:
        """Convert variety_bonus_pct fraction to a basis-point multiplier.

        Formula (architecture §5.3.2):
            bp = 10 000 + int(variety_bonus_pct × 10 000)

        Examples:
            0.00 → 10 000  (1.00×)
            0.075 → 10 750  (1.075×)
            0.30  → 13 000  (1.30×)

        Args:
            variety_bonus_pct: Fraction returned by
                :meth:`calculate_variety_bonus_pct`.

        Returns:
            Integer basis-point multiplier in [10 000, 13 000].
        """
        return 10000 + int(variety_bonus_pct * 10000)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def update_variety_metrics(
        self,
        *,
        user_id: str,
        tracking: StrategyTracking,
    ) -> Tuple[float, float]:
        """Recompute variety score and bonus from *tracking* counts and persist.

        Args:
            user_id:  Owning user UUID (unused directly; kept for call-site
                      symmetry with other services).
            tracking: The ``StrategyTracking`` ORM row to update in-place.

        Returns:
            ``(variety_score, variety_bonus_pct)`` — both as fractions.
        """
        counts: Dict[str, int] = {
            k: int(getattr(tracking, col, 0) or 0)
            for k, col in _STRATEGY_COUNT_COLUMNS.items()
        }

        variety_score = self.calculate_variety_score(counts)
        variety_bonus_pct = self.calculate_variety_bonus_pct(variety_score)

        tracking.variety_score = round(variety_score, 6)
        tracking.variety_bonus_pct = round(variety_bonus_pct, 6)
        tracking.updated_at = _now_utc()

        self.db.flush()

        return variety_score, variety_bonus_pct

    def get_current_variety_bonus(self, user_id: str) -> float:
        """Return the stored ``variety_bonus_pct`` for *user_id*, or 0.0.

        Returns:
            Fraction in [0.0, 0.60]; 0.0 if no tracking row exists.
        """
        tracking = (
            self.db.query(StrategyTracking)
            .filter(StrategyTracking.user_id == user_id)
            .one_or_none()
        )
        if tracking is None or tracking.variety_bonus_pct is None:
            return 0.0
        return float(tracking.variety_bonus_pct)

    def get_current_variety_multiplier_bp(self, user_id: str) -> int:
        """Return the current basis-point multiplier for *user_id*.

        Returns:
            Integer in [10 000, 13 000]; 10 000 if no tracking row exists.
        """
        bonus_pct = self.get_current_variety_bonus(user_id)
        return self.calculate_variety_multiplier_bp(bonus_pct)

    # ------------------------------------------------------------------
    # XP application
    # ------------------------------------------------------------------

    def apply_variety_bonus_to_xp(self, base_xp: int, variety_bonus_pct: float) -> int:
        """Apply variety bonus fraction to *base_xp*.

        Args:
            base_xp:           Base XP amount (before variety adjustment).
            variety_bonus_pct: Fraction from :meth:`calculate_variety_bonus_pct`
                               or :meth:`get_current_variety_bonus` (e.g. 0.30,
                               **not** 30.0).

        Returns:
            ``int(base_xp * (1.0 + variety_bonus_pct))``.
        """
        return int(base_xp * (1.0 + variety_bonus_pct))

    def apply_variety_multiplier_bp(self, base_xp: int, variety_multiplier_bp: int) -> int:
        """Apply a basis-point multiplier to *base_xp* (integer arithmetic).

        Preferred over :meth:`apply_variety_bonus_to_xp` when the caller
        already has the bp value (avoids double conversion).

        Returns:
            ``base_xp * variety_multiplier_bp // 10 000``.
        """
        return base_xp * variety_multiplier_bp // 10000
