"""Balance system API endpoints.

Covers variety metrics, diminishing-returns penalties, and manual window refresh.

Architecture references:
    §5.0.4  Rolling Window Semantics
    §5.3    Variety Score / Bonus
    §5.9    Diminishing Returns (strategy spam penalty)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.ai.steps.strategy import STRATEGY_KEYS
from src.core.balance_diminishing_returns import DiminishingReturnsService
from src.core.balance_window_service import BalanceWindowService
from src.demo_profiles import (
    demo_variety_payload,
    has_demo_profile,
    has_live_profile_activity,
)
from src.db.models.strategy import StrategyTracking
from src.db.session import get_db

router = APIRouter(prefix="/balance", tags=["balance"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class StrategyCountsResponse(BaseModel):
    """Rolling 30-day usage counts for each canonical strategy."""

    social: int
    study: int
    mundane: int
    troll: int
    grind: int
    harmony: int


class VarietyMetricsResponse(BaseModel):
    """Variety score, bonus, strategy counts, and current window boundaries."""

    variety_score: float
    variety_bonus_pct: float
    strategy_counts: StrategyCountsResponse
    window_start_date: Optional[str]
    window_end_date: Optional[str]


class StrategyPenaltiesResponse(BaseModel):
    """Diminishing-returns penalty multipliers and consecutive-day streak counts.

    ``penalties`` values are multipliers in [0.50, 1.00]:
        1.00 = no penalty
        0.85 = −15 % (3–4 consecutive days)
        0.70 = −30 % (5–6 consecutive days)
        0.50 = −50 % / hard floor (7+ consecutive days)

    ``consecutive_days`` is the current streak count for each strategy.
    Both dicts are keyed by canonical short strategy key
    (``social``, ``study``, ``mundane``, ``troll``, ``grind``, ``harmony``).
    """

    penalties: Dict[str, float]
    consecutive_days: Dict[str, int]


class BalanceRefreshResponse(BaseModel):
    """Result returned after a manual window refresh."""

    success: bool
    message: str
    variety_score: float
    variety_bonus_pct: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_tracking(db: Session, user_id: str) -> StrategyTracking:
    """Return the StrategyTracking row for *user_id* or raise 404."""
    tracking = (
        db.query(StrategyTracking)
        .filter(StrategyTracking.user_id == user_id)
        .one_or_none()
    )
    if tracking is None:
        raise HTTPException(
            status_code=404,
            detail=f"No balance data found for user {user_id!r}. "
                   "Submit a journal entry first to initialise tracking.",
        )
    return tracking


def _parse_consecutive_days(tracking: StrategyTracking) -> Dict[str, int]:
    """Extract per-strategy consecutive-day counts from strategy_streaks_json."""
    try:
        streaks: dict = json.loads(tracking.strategy_streaks_json or "{}")
    except (json.JSONDecodeError, TypeError):
        streaks = {}
    return {sk: int((streaks.get(sk) or {}).get("count") or 0) for sk in STRATEGY_KEYS}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/variety",
    response_model=VarietyMetricsResponse,
    summary="Get variety score and rolling strategy counts",
)
def get_variety_metrics(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> VarietyMetricsResponse:
    """Return the current variety score, bonus fraction, per-strategy 30-day
    counts, and window boundaries for *user_id*.

    ``variety_score`` is a normalised Shannon entropy value in [0.0, 1.0].
    ``variety_bonus_pct`` is a stored fraction (e.g. 0.30 = 30 % bonus, not 30).
    """
    if has_demo_profile(user_id) and not has_live_profile_activity(db, user_id):
        payload = demo_variety_payload(user_id)
        if payload is not None:
            return VarietyMetricsResponse(
                variety_score=float(payload["variety_score"]),
                variety_bonus_pct=float(payload["variety_bonus_pct"]),
                strategy_counts=StrategyCountsResponse(**payload["strategy_counts"]),
                window_start_date=payload["window_start_date"],
                window_end_date=payload["window_end_date"],
            )

    tracking = _require_tracking(db, user_id)

    return VarietyMetricsResponse(
        variety_score=float(tracking.variety_score or 0.0),
        variety_bonus_pct=float(tracking.variety_bonus_pct or 0.0),
        strategy_counts=StrategyCountsResponse(
            social=tracking.social_risk_count,
            study=tracking.study_burst_count,
            mundane=tracking.mundane_focus_count,
            troll=tracking.troll_exploits_count,
            grind=tracking.daily_grind_count,
            harmony=tracking.harmony_balance_count,
        ),
        window_start_date=(
            tracking.window_start_date.isoformat()
            if tracking.window_start_date is not None
            else None
        ),
        window_end_date=(
            tracking.window_end_date.isoformat()
            if tracking.window_end_date is not None
            else None
        ),
    )


@router.get(
    "/penalties",
    response_model=StrategyPenaltiesResponse,
    summary="Get diminishing-returns penalties for all strategies",
)
def get_strategy_penalties(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> StrategyPenaltiesResponse:
    """Return XP penalty multipliers and current streak counts for all six
    canonical strategies.

    Returns empty dicts when no tracking row exists for *user_id* (no entries
    submitted yet — no penalty state to report).
    """
    service = DiminishingReturnsService(db)
    penalties = service.get_all_strategy_penalties(user_id)

    if not penalties:
        return StrategyPenaltiesResponse(penalties={}, consecutive_days={})

    tracking = (
        db.query(StrategyTracking)
        .filter(StrategyTracking.user_id == user_id)
        .one_or_none()
    )
    consecutive_days = _parse_consecutive_days(tracking) if tracking is not None else {}

    return StrategyPenaltiesResponse(
        penalties=penalties,
        consecutive_days=consecutive_days,
    )


@router.post(
    "/refresh",
    response_model=BalanceRefreshResponse,
    summary="Manually refresh the 30-day rolling window",
)
def refresh_balance_window(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> BalanceRefreshResponse:
    """Recount all strategies from completed journal entries in the last 30
    user-local days and recompute variety metrics.

    Useful after bulk imports, backfill scripts, or data corrections.  For
    normal operation the pipeline updates counts incrementally via
    ``BalanceWindowService.increment_strategy``.
    """
    service = BalanceWindowService(db)
    try:
        tracking = service.refresh_window(user_id, datetime.now(timezone.utc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return BalanceRefreshResponse(
        success=True,
        message="Balance window refreshed successfully.",
        variety_score=float(tracking.variety_score or 0.0),
        variety_bonus_pct=float(tracking.variety_bonus_pct or 0.0),
    )
