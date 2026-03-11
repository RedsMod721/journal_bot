"""Step 08a — Calculate variety score and variety_multiplier_bp from strategy diversity.

Variety score is computed using Shannon entropy normalised over the 6 balance
strategies (social, study, mundane, troll, grind, harmony) from the cumulative
per-strategy counts in ``StrategyTracking`` (architecture §5.3).

Variety multiplier schedule (architecture §5.3.1–5.3.2, project override)
---------------------------------------------------------
    variety_score     = H / log2(6)             — 0.0 to 1.0
    variety_bonus_pct = score² × 0.30           — 0.0% to 30.0% (base)
    variety_multiplier_bp = 10 000 + int(variety_bonus_pct × 10 000)

    score 0.0 -> bp 10 000  (1.00x — all activity in one strategy)
    score 0.5 -> bp ~10 750  (1.075x — moderate diversity)
    score 1.0 -> bp 13 000  (1.30x — perfectly even distribution)

    Harvest Festival may later double this base bonus to 60% max (1.60x);
    that multiplier is applied separately by the event system, not here.

The step also:
  - Persists computed variety_score and variety_bonus_pct back to the
    StrategyTracking row so the dashboard can read them without recalculating.
  - Upserts the UserAnalytics row for today so the rolling dashboard stays current.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from src.db.models.analytics import UserAnalytics
from src.db.models.strategy import StrategyTracking

# Canonical six balance strategies (architecture section 5.2).
STRATEGY_KEYS = ("social", "study", "mundane", "troll", "grind", "harmony")

# Maps internal strategy key → StrategyTracking column name (architecture §5.0.3).
_STRATEGY_COUNT_COLUMNS: dict[str, str] = {
    "social": "social_risk_count",
    "study": "study_burst_count",
    "mundane": "mundane_focus_count",
    "troll": "troll_exploits_count",
    "grind": "daily_grind_count",
    "harmony": "harmony_balance_count",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Core entropy calculation (matches architecture section 5.3.3 reference impl)
# ---------------------------------------------------------------------------


def calculate_variety_score(strategy_counts: dict[str, int]) -> float:
    """Compute Shannon entropy normalised to [0.0, 1.0] over the 6 strategies.

    Args:
        strategy_counts: Mapping of strategy key to cumulative usage count.
                         Missing keys are treated as count=0.

    Returns:
        Float in [0.0, 1.0]. 0.0 = all activity in one strategy; 1.0 = even.
    """
    total = sum(int(strategy_counts.get(k, 0)) for k in STRATEGY_KEYS)
    if total <= 0:
        return 0.0
    proportions = [
        strategy_counts[k] / total
        for k in STRATEGY_KEYS
        if strategy_counts.get(k, 0) > 0
    ]
    entropy = -sum(p * math.log2(p) for p in proportions)
    max_entropy = math.log2(len(STRATEGY_KEYS))  # log2(6)
    return float(entropy / max_entropy)


# ---------------------------------------------------------------------------
# Public step function
# ---------------------------------------------------------------------------


def run(
    *,
    user_id: str,
    db: Session,
    window_days: int = 30,
) -> dict[str, Any]:
    """Compute variety_multiplier_bp from cumulative strategy diversity.

    Reads per-strategy counts from the StrategyTracking pivot row, applies
    Shannon entropy normalisation (section 5.3.1), converts to a quadratic
    bonus (section 5.3.2), then expresses the result in basis points.
    Persists variety_score and variety_bonus_pct back to the row.

    Args:
        user_id:     Owning user UUID.
        db:          SQLAlchemy session (write - issues a flush for analytics).
        window_days: Retained for API compatibility; not used in entropy calc.

    Returns:
        Dict with keys:
            variety_score         -- float 0.0-1.0 (normalised Shannon entropy).
            variety_bonus_pct     -- float 0.0-0.30 (base cap; 0.60 only via future event arc).
            variety_multiplier_bp -- int, 10 000-13 000 bp (base).
            strategy_counts       -- dict of strategy_key -> count.
            window_days           -- echo of the input parameter (API compat).
    """
    row = (
        db.query(StrategyTracking)
        .filter(StrategyTracking.user_id == user_id)
        .one_or_none()
    )

    if row is not None:
        strategy_counts: dict[str, int] = {
            k: int(getattr(row, col, 0) or 0)
            for k, col in _STRATEGY_COUNT_COLUMNS.items()
        }
    else:
        strategy_counts = {}

    variety_score = calculate_variety_score(strategy_counts)
    variety_bonus_pct = (variety_score**2) * 0.30
    variety_multiplier_bp = 10000 + int(variety_bonus_pct * 10000)

    # Persist computed metrics back to the row so the dashboard can read
    # variety_score / variety_bonus_pct without re-running the pipeline.
    if row is not None:
        row.variety_score = round(variety_score, 6)
        row.variety_bonus_pct = round(variety_bonus_pct, 6)
        # Refresh window_end_date to today
        today = _now_utc().date()
        row.window_end_date = today
        row.window_start_date = today - timedelta(days=window_days)

    _upsert_daily_analytics(
        user_id=user_id,
        active_strategies_count=len([v for v in strategy_counts.values() if v > 0]),
        db=db,
    )

    return {
        "variety_score": round(variety_score, 6),
        "variety_bonus_pct": round(variety_bonus_pct, 6),
        "variety_multiplier_bp": variety_multiplier_bp,
        "strategy_counts": strategy_counts,
        "window_days": window_days,
    }


def _upsert_daily_analytics(
    *, user_id: str, active_strategies_count: int, db: Session
) -> None:
    """Upsert the UserAnalytics row for today (YYYY-MM-DD key)."""
    day_key = _now_utc().strftime("%Y-%m-%d")
    row = (
        db.query(UserAnalytics)
        .filter(
            UserAnalytics.user_id == user_id,
            UserAnalytics.day_key == day_key,
        )
        .one_or_none()
    )
    if row is None:
        row = UserAnalytics(
            user_id=user_id,
            day_key=day_key,
            entries_count=1,
            xp_awarded_total=0,
            active_skills_count=active_strategies_count,
        )
        db.add(row)
    else:
        row.entries_count += 1
        row.active_skills_count = active_strategies_count
        row.updated_at = _now_utc()
    db.flush()
