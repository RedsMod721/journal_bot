"""
Story arcs API endpoints.

Implements Section 8.8 (API Endpoints) from architecture.

Authorization note: until a real auth layer exists, the caller identifies
themselves via the ``user_id`` query parameter — matching the convention used
by every other route in this project.  Cross-user access returns 404 to avoid
existence leakage (Section 8.8.0).
"""

from __future__ import annotations

import base64
import json
import re
import uuid as _uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from src.core.arc_lifecycle import ArcLifecycleService
from src.core.arc_vacation import VacationModeService
from src.db.models.story import StoryArc
from src.db.session import get_db

router = APIRouter(prefix="/arcs", tags=["story_arcs"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ARC_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _validate_arc_id(arc_id: str) -> None:
    """Raise 422 if *arc_id* is not a valid UUID string."""
    try:
        _uuid.UUID(arc_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "INVALID_ID_FORMAT",
                    "message": "arc_id must be a valid UUID",
                }
            },
        )


def _get_arc_for_user(db: Session, arc_id: str, user_id: str) -> StoryArc:
    """Return the arc, or 404 if missing or owned by a different user."""
    arc = db.query(StoryArc).filter(StoryArc.id == arc_id).first()
    if arc is None or arc.user_id != user_id:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "ARC_NOT_FOUND",
                    "message": "Arc not found",
                }
            },
        )
    return arc


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ArcResponse(BaseModel):
    """Story arc response (Section 8.8)."""

    id: str
    arc_type: str
    status: str
    event_name: Optional[str] = None
    theme_ids: list[str] = []
    xp_requirement_multiplier: float
    xp_reward_multiplier: float
    decay_rate_multiplier: float
    started_at: str
    duration_days: Optional[float] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None

    @classmethod
    def from_arc(cls, arc: StoryArc) -> "ArcResponse":
        return cls(
            id=arc.id,
            arc_type=arc.arc_type,
            status=arc.status,
            event_name=arc.event_name,
            theme_ids=arc.theme_ids_list,
            xp_requirement_multiplier=arc.xp_requirement_multiplier,
            xp_reward_multiplier=arc.xp_reward_multiplier,
            decay_rate_multiplier=arc.decay_rate_multiplier,
            started_at=arc.started_at,
            duration_days=arc.duration_days,
            created_at=arc.created_at,
            updated_at=arc.updated_at,
            completed_at=arc.completed_at,
        )


class CurrentArcResponse(BaseModel):
    active: bool
    arc: Optional[ArcResponse] = None


class ArcHistoryResponse(BaseModel):
    items: list[ArcResponse]
    next_cursor: Optional[str] = None


class CreateEventArcRequest(BaseModel):
    event_name: str = Field(..., min_length=1, max_length=100)
    theme_ids: list[str] = Field(default_factory=list)
    duration_days: Optional[float] = Field(None, ge=0.1, le=365)
    xp_requirement_multiplier: float = Field(1.0, ge=0.1, le=5.0)
    xp_reward_multiplier: float = Field(1.0, ge=0.1, le=5.0)
    decay_rate_multiplier: float = Field(1.0, ge=0.0, le=2.0)

    @field_validator("theme_ids")
    @classmethod
    def validate_theme_ids(cls, v: list[str]) -> list[str]:
        for tid in v:
            try:
                _uuid.UUID(tid)
            except ValueError:
                raise ValueError(f"Invalid theme_id format: {tid!r}")
        return v


class ActivateVacationRequest(BaseModel):
    duration_days: Optional[float] = Field(None, ge=0.1, le=365)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/current", response_model=CurrentArcResponse)
def get_current_arc(
    user_id: Annotated[str, Query(description="Owner user UUID")],
    db: Session = Depends(get_db),
) -> CurrentArcResponse:
    """
    Get the current active arc (Section 8.8.1).

    Returns ``{"active": false, "arc": null}`` when no arc is active.
    """
    lifecycle = ArcLifecycleService(db)
    active_arc = lifecycle.get_active_arc(user_id)

    if active_arc is None:
        return CurrentArcResponse(active=False, arc=None)

    return CurrentArcResponse(active=True, arc=ArcResponse.from_arc(active_arc))


@router.get("/history", response_model=ArcHistoryResponse)
def get_arc_history(
    user_id: Annotated[str, Query(description="Owner user UUID")],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Optional[str] = None,
    db: Session = Depends(get_db),
) -> ArcHistoryResponse:
    """
    Get arc history with seek-based cursor pagination (Section 8.8.2).

    Ordering: started_at DESC, updated_at DESC, id DESC
    """
    query = db.query(StoryArc).filter(StoryArc.user_id == user_id)

    if cursor is not None:
        try:
            # Pad base64url to a multiple of 4 bytes before decoding.
            padding = 4 - len(cursor) % 4
            cursor_json = base64.urlsafe_b64decode(cursor + "=" * padding).decode()
            c = json.loads(cursor_json)
            c_started = c["started_at"]
            c_updated = c["updated_at"]
            c_id = c["id"]
        except Exception:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "INVALID_CURSOR",
                        "message": "Invalid pagination cursor",
                    }
                },
            )

        # Seek predicate — rows that come *after* the cursor position.
        query = query.filter(
            or_(
                StoryArc.started_at < c_started,
                and_(
                    StoryArc.started_at == c_started,
                    StoryArc.updated_at < c_updated,
                ),
                and_(
                    StoryArc.started_at == c_started,
                    StoryArc.updated_at == c_updated,
                    StoryArc.id < c_id,
                ),
            )
        )

    query = query.order_by(
        StoryArc.started_at.desc(),
        StoryArc.updated_at.desc(),
        StoryArc.id.desc(),
    )

    # Fetch one extra to detect whether another page exists.
    rows = query.limit(limit + 1).all()

    next_cursor: Optional[str] = None
    if len(rows) > limit:
        last = rows[limit - 1]
        cursor_data = json.dumps(
            {"started_at": last.started_at, "updated_at": last.updated_at, "id": last.id},
            separators=(",", ":"),
        )
        next_cursor = (
            base64.urlsafe_b64encode(cursor_data.encode()).decode().rstrip("=")
        )
        rows = rows[:limit]

    return ArcHistoryResponse(
        items=[ArcResponse.from_arc(a) for a in rows],
        next_cursor=next_cursor,
    )


@router.post("/event", response_model=ArcResponse, status_code=201)
def create_event_arc(
    request: CreateEventArcRequest,
    user_id: Annotated[str, Query(description="Owner user UUID")],
    idempotency_key: Annotated[Optional[str], Header(alias="Idempotency-Key")] = None,
    db: Session = Depends(get_db),
) -> ArcResponse:
    """
    Create a user-declared event arc (Section 8.8.3).

    Atomically replaces any existing active arc (non-vacation arcs are
    abandoned; see ArcLifecycleService.create_arc).
    """
    lifecycle = ArcLifecycleService(db)

    arc = lifecycle.create_arc(
        user_id=user_id,
        arc_type="event",
        event_name=request.event_name,
        theme_ids=request.theme_ids or None,
        duration_days=request.duration_days,
        xp_requirement_multiplier_bp=int(request.xp_requirement_multiplier * 10_000),
        xp_reward_multiplier_bp=int(request.xp_reward_multiplier * 10_000),
        decay_rate_multiplier_bp=int(request.decay_rate_multiplier * 10_000),
        make_active=True,
    )

    # Append immutable audit trigger for the manual event creation.
    lifecycle._write_trigger(
        arc_id=arc.id,
        user_id=user_id,
        trigger_type="manual_event",
        trigger_data={
            "event_name": request.event_name,
            **({"idempotency_key": idempotency_key} if idempotency_key else {}),
        },
    )
    db.commit()

    return ArcResponse.from_arc(arc)


@router.post("/{arc_id}/end", response_model=ArcResponse)
def end_arc(
    arc_id: str,
    user_id: Annotated[str, Query(description="Owner user UUID")],
    db: Session = Depends(get_db),
) -> ArcResponse:
    """
    End an event arc early as completed (Section 8.8.4).

    Only non-vacation event arcs in active status may be ended this way.
    Use POST /vacation/end to close a vacation arc.
    """
    _validate_arc_id(arc_id)
    arc = _get_arc_for_user(db, arc_id, user_id)

    if arc.arc_type != "event" or arc.event_name == "vacation_mode":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_ARC_TYPE",
                    "message": "Only non-vacation event arcs can be ended with this endpoint",
                }
            },
        )

    if arc.status != "active":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "ARC_NOT_ACTIVE",
                    "message": "Arc is not active",
                }
            },
        )

    lifecycle = ArcLifecycleService(db)
    arc = lifecycle.complete_arc(
        arc=arc,
        trigger_type="user_end",
        trigger_data={"reason": "user_ended_early"},
    )
    db.commit()

    return ArcResponse.from_arc(arc)


@router.post("/{arc_id}/abandon", response_model=ArcResponse)
def abandon_arc(
    arc_id: str,
    user_id: Annotated[str, Query(description="Owner user UUID")],
    db: Session = Depends(get_db),
) -> ArcResponse:
    """
    Abandon an arc (Section 8.8.5).

    Sets status to 'abandoned' (terminal). Cannot abandon already-terminal arcs.
    """
    _validate_arc_id(arc_id)
    arc = _get_arc_for_user(db, arc_id, user_id)

    if arc.status in ("completed", "abandoned"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "ARC_ALREADY_TERMINAL",
                    "message": "Arc is already completed or abandoned",
                }
            },
        )

    lifecycle = ArcLifecycleService(db)
    arc = lifecycle.abandon_arc(arc=arc, reason="user_abandon")
    db.commit()

    return ArcResponse.from_arc(arc)


@router.post("/vacation/activate", response_model=ArcResponse, status_code=201)
def activate_vacation(
    request: ActivateVacationRequest,
    user_id: Annotated[str, Query(description="Owner user UUID")],
    db: Session = Depends(get_db),
) -> ArcResponse:
    """
    Activate vacation mode (Section 8.8.6).

    Pauses the current arc and creates a vacation event arc with
    ``decay_rate_multiplier = 0`` (no skill decay during vacation).
    Idempotent: returns the existing vacation arc if already active.
    """
    vacation_service = VacationModeService(db)
    vacation_arc, _paused_arc = vacation_service.activate_vacation(
        user_id=user_id,
        duration_days=request.duration_days,
    )
    db.commit()
    return ArcResponse.from_arc(vacation_arc)


@router.post("/vacation/end", response_model=ArcResponse)
def end_vacation(
    user_id: Annotated[str, Query(description="Owner user UUID")],
    db: Session = Depends(get_db),
) -> ArcResponse:
    """
    End vacation mode (Section 8.8.7).

    Completes the vacation arc and resumes the previously paused arc.
    Returns the completed vacation arc.
    """
    vacation_service = VacationModeService(db)
    try:
        ended_vacation, _resumed_arc = vacation_service.end_vacation(user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "NO_ACTIVE_VACATION",
                    "message": str(exc),
                }
            },
        )
    db.commit()
    return ArcResponse.from_arc(ended_vacation)
