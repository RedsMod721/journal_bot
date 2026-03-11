"""Harmony system API endpoints.

Covers current dimension scores, manual refresh, historical snapshots,
and overwork status with recommendations.

Architecture references:
    §6    Harmony System
    §6.4  Overwork Detection
    §6.6  Update Lifecycle
    §6.7  Snapshots
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.harmony_refresh_service import HarmonyRefreshService
from src.demo_profiles import (
    demo_harmony_payload,
    has_demo_profile,
    has_live_profile_activity,
)
from src.db.models.harmony import HarmonyDimension, HarmonySnapshot
from src.db.session import get_db

router = APIRouter(prefix="/harmony", tags=["harmony"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DimensionScores(BaseModel):
    physical: float
    mental: float
    social: float
    productivity: float
    rest: float
    growth: float
    creative: float


class HarmonyResponse(BaseModel):
    user_id: str
    dimensions: DimensionScores
    overall_balance: float
    overwork_stage: int
    overwork_consecutive_days: int
    updated_at: str


class HarmonySnapshotResponse(BaseModel):
    id: str
    user_id: str
    snapshot_date: str
    dimensions: DimensionScores
    overall_balance: float
    created_at: str


class HarmonyRefreshResponse(BaseModel):
    success: bool
    message: str
    overall_balance: float
    overwork_stage: int


class OverworkStatusResponse(BaseModel):
    stage: int
    stage_name: str
    consecutive_days: int
    productivity: float
    rest: float
    message: str
    recommendations: List[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STAGE_INFO = {
    0: {
        "name": "Normal",
        "message": "You're maintaining a healthy balance",
        "recommendations": [],
    },
    1: {
        "name": "Watch",
        "message": "Productivity is high. Monitor your rest.",
        "recommendations": [
            "Consider taking short breaks",
            "Ensure adequate sleep",
        ],
    },
    2: {
        "name": "Warning",
        "message": "Overwork pattern detected. Rest is important.",
        "recommendations": [
            "Schedule rest activities",
            "Reduce work hours if possible",
            "Practice stress management",
        ],
    },
    3: {
        "name": "Crisis",
        "message": "Serious overwork detected. Immediate rest needed.",
        "recommendations": [
            "Take time off if possible",
            "Seek support from therapist or counselor",
            "Prioritize recovery activities",
            "Consider medical consultation if symptoms persist",
        ],
    },
}


def _dim_scores(obj: HarmonyDimension | HarmonySnapshot) -> DimensionScores:
    return DimensionScores(
        physical=obj.physical,
        mental=obj.mental,
        social=obj.social,
        productivity=obj.productivity,
        rest=obj.rest,
        growth=obj.growth,
        creative=obj.creative,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/dimensions",
    response_model=HarmonyResponse,
    summary="Get current harmony dimensions for a user",
)
def get_harmony_dimensions(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> HarmonyResponse:
    """Return the current 7-dimension harmony state for *user_id*.

    Creates a default row (all scores 0.5, stage 0) when none exists yet.
    """
    if has_demo_profile(user_id) and not has_live_profile_activity(db, user_id):
        payload = demo_harmony_payload(user_id)
        if payload is not None:
            return HarmonyResponse(
                user_id=payload["user_id"],
                dimensions=DimensionScores(**payload["dimensions"]),
                overall_balance=payload["overall_balance"],
                overwork_stage=payload["overwork_stage"],
                overwork_consecutive_days=payload["overwork_consecutive_days"],
                updated_at=payload["updated_at"],
            )

    service = HarmonyRefreshService(db)
    try:
        result = service.refresh_harmony(
            user_id,
            datetime.now(timezone.utc),
            advance_overwork_state=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    harmony = result.harmony

    return HarmonyResponse(
        user_id=harmony.user_id,
        dimensions=_dim_scores(harmony),
        overall_balance=harmony.overall_balance,
        overwork_stage=result.overwork.stage,
        overwork_consecutive_days=result.overwork.consecutive_days,
        updated_at=harmony.updated_at.isoformat(),
    )


@router.post(
    "/refresh",
    response_model=HarmonyRefreshResponse,
    summary="Manually refresh harmony dimensions",
)
def refresh_harmony(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> HarmonyRefreshResponse:
    """Recalculate harmony scores from the 30-day journal window.

    Does NOT advance the overwork stage (read-only refresh).  The pipeline
    advances the overwork stage automatically when processing new entries.
    """
    service = HarmonyRefreshService(db)
    try:
        result = service.refresh_harmony(
            user_id, datetime.now(timezone.utc), advance_overwork_state=False
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return HarmonyRefreshResponse(
        success=True,
        message="Harmony refreshed",
        overall_balance=result.harmony.overall_balance,
        overwork_stage=result.overwork.stage,
    )


@router.get(
    "/snapshots",
    response_model=List[HarmonySnapshotResponse],
    summary="Get daily harmony snapshots (last N days)",
)
def get_harmony_snapshots(
    user_id: Annotated[str, Query(description="User UUID")],
    days: Annotated[int, Query(description="Number of days to retrieve", ge=1, le=365)] = 30,
    db: Session = Depends(get_db),
) -> List[HarmonySnapshotResponse]:
    """Return daily snapshots for *user_id* ordered newest-first."""
    service = HarmonyRefreshService(db)
    try:
        end_date = service.user_local_today(user_id, datetime.now(timezone.utc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    start_date = end_date - timedelta(days=days)

    snapshots = (
        db.query(HarmonySnapshot)
        .filter(
            HarmonySnapshot.user_id == user_id,
            HarmonySnapshot.snapshot_date >= start_date,
            HarmonySnapshot.snapshot_date <= end_date,
        )
        .order_by(HarmonySnapshot.snapshot_date.desc())
        .all()
    )

    return [
        HarmonySnapshotResponse(
            id=s.id,
            user_id=s.user_id,
            snapshot_date=s.snapshot_date.isoformat(),
            dimensions=_dim_scores(s),
            overall_balance=s.overall_balance,
            created_at=s.created_at.isoformat(),
        )
        for s in snapshots
    ]


@router.get(
    "/overwork-status",
    response_model=OverworkStatusResponse,
    summary="Get overwork stage with recommendations",
)
def get_overwork_status(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> OverworkStatusResponse:
    """Return the current overwork stage, consecutive-day count, and
    actionable recommendations for *user_id*.

    Returns stage 0 (Normal) with empty recommendations when no harmony
    row exists for the user yet.
    """
    if has_demo_profile(user_id) and not has_live_profile_activity(db, user_id):
        payload = demo_harmony_payload(user_id)
        if payload is not None:
            stage = int(payload["overwork_stage"])
            info = _STAGE_INFO[stage]
            return OverworkStatusResponse(
                stage=stage,
                stage_name=info["name"],
                consecutive_days=int(payload["overwork_consecutive_days"]),
                productivity=float(payload["dimensions"]["productivity"]),
                rest=float(payload["dimensions"]["rest"]),
                message=info["message"],
                recommendations=info["recommendations"],
            )

    service = HarmonyRefreshService(db)
    try:
        result = service.refresh_harmony(
            user_id,
            datetime.now(timezone.utc),
            advance_overwork_state=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    harmony = result.harmony
    stage = result.overwork.stage
    info = _STAGE_INFO[stage]

    return OverworkStatusResponse(
        stage=stage,
        stage_name=info["name"],
        consecutive_days=result.overwork.consecutive_days,
        productivity=harmony.productivity,
        rest=harmony.rest,
        message=info["message"],
        recommendations=info["recommendations"],
    )
