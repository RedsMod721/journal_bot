"""Personality API endpoints.

Read/update operations for personality state and message retrieval.

Architecture references:
    §3.4.1  GET /personality/state
    §3.4.3  POST /personality/feedback
    §3.4.2  GET /personality/messages
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.personality_likability import LikabilityService
from src.db.models.personality import PersonalityMessage, PersonalityState
from src.db.session import get_db

router = APIRouter(prefix="/personality", tags=["personality"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PersonalityStateResponse(BaseModel):
    active_personality: str
    likability_scores: Dict[str, int]
    switch_cooldown_seconds: int
    multi_personality_annotations: int


class LikabilityUpdateRequest(BaseModel):
    message_id: str
    feedback_type: str  # thumbs_up | thumbs_down | explicit_positive | explicit_negative


class LikabilityFeedbackResponse(BaseModel):
    personality: str
    old_likability: int
    new_likability: int
    delta: int
    impact_multiplier: float


class PersonalityMessageResponse(BaseModel):
    id: str
    entry_id: str
    personality: str
    message_type: str
    message_text: str
    context_data: Dict[str, object]
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_or_create_state(user_id: str, db: Session) -> PersonalityState:
    state = db.query(PersonalityState).filter(PersonalityState.user_id == user_id).first()
    if not state:
        state = PersonalityState(user_id=user_id)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def _state_to_response(state: PersonalityState) -> PersonalityStateResponse:
    return PersonalityStateResponse(
        active_personality=state.active_personality,
        likability_scores={
            "observer": state.likability_observer,
            "therapist": state.likability_therapist,
            "coach": state.likability_coach,
            "sassy": state.likability_sassy,
            "wargod": state.likability_wargod,
            "raphael": state.likability_raphael,
        },
        switch_cooldown_seconds=state.switch_cooldown_seconds,
        multi_personality_annotations=state.multi_personality_annotations,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/state", response_model=PersonalityStateResponse)
def get_personality_state(
    user_id: str = Query(..., description="User UUID"),
    db: Session = Depends(get_db),
) -> PersonalityStateResponse:
    """Get current personality state for a user.

    Creates a default state row if none exists yet.
    """
    state = _get_or_create_state(user_id, db)
    return _state_to_response(state)


@router.post("/feedback", response_model=LikabilityFeedbackResponse)
def apply_likability_feedback(
    user_id: str = Query(..., description="User UUID"),
    request: LikabilityUpdateRequest = ...,
    db: Session = Depends(get_db),
) -> LikabilityFeedbackResponse:
    """Apply user feedback to personality likability scores.

    feedback_type values and their deltas:
        thumbs_up         +5
        thumbs_down       -10
        explicit_positive +10
        explicit_negative -15

    Raises:
        404  — message_id not found or does not belong to user_id.
        422  — invalid feedback_type.
    """
    valid_types = {"thumbs_up", "thumbs_down", "explicit_positive", "explicit_negative"}
    if request.feedback_type not in valid_types:
        raise HTTPException(
            status_code=422,
            detail=f"feedback_type must be one of {sorted(valid_types)}",
        )

    service = LikabilityService(db)
    try:
        result = service.apply_feedback(
            user_id=user_id,
            message_id=request.message_id,
            feedback_type=request.feedback_type,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return LikabilityFeedbackResponse(**result)


@router.get("/messages", response_model=List[PersonalityMessageResponse])
def get_personality_messages(
    user_id: str = Query(..., description="User UUID"),
    entry_id: Optional[str] = Query(None, description="Filter to a single journal entry"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    db: Session = Depends(get_db),
) -> List[PersonalityMessageResponse]:
    """Get personality messages for a user, newest first.

    Optionally filtered to a single journal entry via entry_id.
    """
    q = db.query(PersonalityMessage).filter(PersonalityMessage.user_id == user_id)

    if entry_id is not None:
        q = q.filter(PersonalityMessage.entry_id == entry_id)

    messages = q.order_by(PersonalityMessage.created_at.desc()).limit(limit).all()

    return [
        PersonalityMessageResponse(
            id=m.id,
            entry_id=m.entry_id,
            personality=m.personality,
            message_type=m.message_type,
            message_text=m.message_text,
            context_data=json.loads(m.context_data or "{}"),
            created_at=m.created_at.isoformat() + "Z",
        )
        for m in messages
    ]
