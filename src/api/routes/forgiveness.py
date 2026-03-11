"""Forgiveness system API endpoints.

Covers preset management, config get/update, decay statistics, and snapshot history.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.forgiveness_config_service import ForgivenessConfigService
from src.core.forgiveness_presets import FORGIVENESS_PRESET_NAMES, FORGIVENESS_PRESETS
from src.db.models.forgiveness import DecaySnapshot, ForgivenessConfig
from src.db.models.insight import Insight
from src.db.models.skill import Skill
from src.db.session import get_db

router = APIRouter(prefix="/forgiveness", tags=["forgiveness"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PresetInfo(BaseModel):
    preset: str
    name: str
    skill_decay_rate: float
    skill_grace_days: int
    insight_decay_rate: float
    insight_grace_days: int
    critical_threshold: float


class ForgivenessConfigResponse(BaseModel):
    id: str
    user_id: str
    preset: str
    skill_decay_rate: float
    skill_grace_period_days: int
    insight_decay_rate: float
    insight_grace_period_days: int
    critical_staleness_threshold: float
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class UpdatePresetRequest(BaseModel):
    preset: str


class UpdateCustomParamsRequest(BaseModel):
    skill_decay_rate: Optional[float] = None
    skill_grace_days: Optional[int] = None
    insight_decay_rate: Optional[float] = None
    insight_grace_days: Optional[int] = None
    critical_threshold: Optional[float] = None


class DecaySnapshotResponse(BaseModel):
    id: str
    user_id: str
    snapshot_date: str
    average_skill_staleness: Optional[float]
    average_insight_staleness: Optional[float]
    skills_near_critical: Optional[int]
    created_at: str

    model_config = {"from_attributes": True}


class DecayStatsResponse(BaseModel):
    total_skills: int
    critical_skills: int
    stale_skills: int
    avg_staleness: float
    total_insights: int
    weak_insights: int
    avg_insight_strength: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_to_response(config: ForgivenessConfig) -> ForgivenessConfigResponse:
    return ForgivenessConfigResponse(
        id=config.id,
        user_id=config.user_id,
        preset=config.preset,
        skill_decay_rate=config.skill_decay_rate,
        skill_grace_period_days=config.skill_grace_period_days,
        insight_decay_rate=config.insight_decay_rate,
        insight_grace_period_days=config.insight_grace_period_days,
        critical_staleness_threshold=config.critical_staleness_threshold,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/presets", response_model=List[PresetInfo], summary="List available forgiveness presets")
def get_available_presets() -> List[PresetInfo]:
    """Return parameters for all named presets plus a *custom* placeholder."""
    result = [
        PresetInfo(
            preset=name,
            name=FORGIVENESS_PRESET_NAMES[name],
            skill_decay_rate=params.skill_decay_rate,
            skill_grace_days=params.skill_grace_days,
            insight_decay_rate=params.insight_decay_rate,
            insight_grace_days=params.insight_grace_days,
            critical_threshold=params.critical_threshold,
        )
        for name, params in FORGIVENESS_PRESETS.items()
    ]
    return result


@router.get("/config", response_model=ForgivenessConfigResponse, summary="Get user forgiveness config")
def get_config(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> ForgivenessConfigResponse:
    """Return (or auto-create) the forgiveness configuration for *user_id*."""
    service = ForgivenessConfigService(db)
    try:
        config = service.get_or_create_config(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _config_to_response(config)


@router.post("/config/preset", response_model=ForgivenessConfigResponse, summary="Switch forgiveness preset")
def update_preset(
    request: UpdatePresetRequest,
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> ForgivenessConfigResponse:
    """Change the user's active forgiveness preset.  Non-*custom* presets reset stored rates."""
    service = ForgivenessConfigService(db)
    try:
        config = service.update_preset(user_id, request.preset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _config_to_response(config)


@router.post("/config/custom", response_model=ForgivenessConfigResponse, summary="Update custom preset parameters")
def update_custom_params(
    request: UpdateCustomParamsRequest,
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> ForgivenessConfigResponse:
    """Patch individual rate/threshold values.  Requires preset == *custom*."""
    service = ForgivenessConfigService(db)
    try:
        config = service.update_custom_params(
            user_id=user_id,
            skill_decay_rate=request.skill_decay_rate,
            skill_grace_days=request.skill_grace_days,
            insight_decay_rate=request.insight_decay_rate,
            insight_grace_days=request.insight_grace_days,
            critical_threshold=request.critical_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _config_to_response(config)


@router.get("/stats", response_model=DecayStatsResponse, summary="Current decay statistics")
def get_decay_stats(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> DecayStatsResponse:
    """Return live staleness/strength aggregates computed from current skill and insight rows."""
    service = ForgivenessConfigService(db)
    try:
        config = service.get_or_create_config(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    skills = db.query(Skill).filter(Skill.user_id == user_id).all()
    threshold = config.critical_staleness_threshold
    critical_count = sum(1 for s in skills if s.staleness >= threshold)
    # "stale" = approaching critical (within 10 pp below threshold)
    stale_count = sum(
        1 for s in skills if threshold - 0.10 <= s.staleness < threshold
    )
    avg_staleness = sum(s.staleness for s in skills) / len(skills) if skills else 0.0

    insights = (
        db.query(Insight)
        .filter(Insight.user_id == user_id, Insight.status == "active")
        .all()
    )
    weak_count = sum(1 for i in insights if i.strength < 0.5)
    avg_strength = (
        sum(i.strength for i in insights) / len(insights) if insights else 1.0
    )

    return DecayStatsResponse(
        total_skills=len(skills),
        critical_skills=critical_count,
        stale_skills=stale_count,
        avg_staleness=avg_staleness,
        total_insights=len(insights),
        weak_insights=weak_count,
        avg_insight_strength=avg_strength,
    )


@router.get("/snapshots", response_model=List[DecaySnapshotResponse], summary="Decay snapshot history")
def get_snapshots(
    user_id: Annotated[str, Query(description="User UUID")],
    days: int = Query(30, ge=1, le=365, description="Number of days to retrieve"),
    db: Session = Depends(get_db),
) -> List[DecaySnapshotResponse]:
    """Return daily decay snapshots for *user_id* covering the last *days* days."""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # snapshot_date is stored as ISO string (YYYY-MM-DD)
    snapshots = (
        db.query(DecaySnapshot)
        .filter(
            DecaySnapshot.user_id == user_id,
            DecaySnapshot.snapshot_date >= start_date.isoformat(),
            DecaySnapshot.snapshot_date <= end_date.isoformat(),
        )
        .order_by(DecaySnapshot.snapshot_date.desc())
        .all()
    )

    return [
        DecaySnapshotResponse(
            id=s.id,
            user_id=s.user_id,
            snapshot_date=s.snapshot_date,
            average_skill_staleness=s.average_skill_staleness,
            average_insight_staleness=s.average_insight_staleness,
            skills_near_critical=s.skills_near_critical,
            created_at=s.created_at.isoformat(),
        )
        for s in snapshots
    ]
