"""Skill API endpoints used by the Week 4 UI/CLI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.enums import SkillState
from src.core.skill_unlocks import SkillUnlockService
from src.core.xp import (
    calculate_xp_for_level,
    effective_level_from_xp,
    effective_rank_from_xp,
)
from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill
from src.db.models.user import User
from src.db.models.user_skill_state import UserSkillState
from src.db.session import get_db

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillResponse(BaseModel):
    skill_id: str
    user_id: str
    canonical_name: str
    category: str
    total_xp: int
    current_level: int
    rank: Optional[str] = None
    current_level_xp: int
    next_level_xp: int
    last_practiced_at: datetime
    created_at: datetime


class SkillStateResponse(BaseModel):
    skill_id: str
    canonical_name: str
    hierarchy_level: int
    state: str
    user_blocked: bool
    parent_skill_ids: List[str]
    discovered_at: Optional[str] = None
    unlocked_at: Optional[str] = None
    activated_at: Optional[str] = None
    total_xp: Optional[int] = None
    current_level: Optional[int] = None
    rank: Optional[str] = None


class HierarchyNodeResponse(BaseModel):
    skill_id: str
    canonical_name: str
    hierarchy_level: int
    parent_skill_ids: List[str]
    state: str
    user_blocked: bool
    total_xp: int
    current_level: int
    rank: Optional[str] = None
    current_level_xp: int
    next_level_xp: int


class UnlockInfoResponse(BaseModel):
    skill_id: str
    canonical_name: str
    hierarchy_level: int
    current_state: str
    can_unlock: bool
    parent_progress: List[dict]
    required_parent_level: int
    user_blocked: bool


class BlockSkillRequest(BaseModel):
    blocked: bool


def _skill_to_response(skill: Skill, category: str) -> SkillResponse:
    last_practiced = skill.last_activity_at or skill.updated_at or skill.created_at
    if last_practiced.tzinfo is None:
        last_practiced = last_practiced.replace(tzinfo=timezone.utc)
    total_xp = int(skill.xp)
    current_level = effective_level_from_xp(total_xp)
    if current_level <= 0:
        current_level_floor = 0
        next_level_floor = calculate_xp_for_level(2)
    else:
        current_level_floor = calculate_xp_for_level(current_level)
        next_level_floor = calculate_xp_for_level(current_level + 1)

    return SkillResponse(
        skill_id=skill.id,
        user_id=skill.user_id,
        canonical_name=skill.name or skill.canonical_name,
        category=category,
        total_xp=total_xp,
        current_level=current_level,
        rank=effective_rank_from_xp(total_xp),
        current_level_xp=max(0, total_xp - current_level_floor),
        next_level_xp=max(1, next_level_floor - current_level_floor),
        last_practiced_at=last_practiced,
        created_at=skill.created_at,
    )


@router.get("/hierarchy", response_model=List[HierarchyNodeResponse], summary="Full skill hierarchy with states")
def get_skill_hierarchy(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> List[HierarchyNodeResponse]:
    """Return all skills in the hierarchy with their current unlock states."""
    unlock_service = SkillUnlockService(db)

    # Build a source_skill_id → Skill lookup in one query to avoid N+1
    global_id_to_skill: dict[str, Skill] = {
        s.global_skill_id: s
        for s in db.query(Skill).filter(
            Skill.user_id == user_id,
            Skill.global_skill_id.isnot(None),
        ).all()
    }

    result = []
    for source_id, skill_info in unlock_service.hierarchy.items():
        state = unlock_service.get_or_create_skill_state(user_id, source_id)
        global_id = unlock_service._resolve_global_id(source_id)
        skill = global_id_to_skill.get(global_id) if global_id else None
        total_xp = int(skill.xp) if skill else 0
        current_level = effective_level_from_xp(total_xp)
        if current_level <= 0:
            current_level_floor = 0
            next_level_floor = calculate_xp_for_level(2)
        else:
            current_level_floor = calculate_xp_for_level(current_level)
            next_level_floor = calculate_xp_for_level(current_level + 1)
        current_level_xp = max(0, total_xp - current_level_floor)
        next_level_xp = max(1, next_level_floor - current_level_floor)

        result.append(
            HierarchyNodeResponse(
                skill_id=source_id,
                canonical_name=skill_info["canonical_name"],
                hierarchy_level=skill_info["hierarchy_level"],
                parent_skill_ids=skill_info.get("parent_skill_ids", []),
                state=state.state if state else SkillState.LOCKED,
                user_blocked=state.user_blocked if state else False,
                total_xp=total_xp,
                current_level=current_level,
                rank=effective_rank_from_xp(total_xp),
                current_level_xp=current_level_xp,
                next_level_xp=next_level_xp,
            )
        )
    return result


@router.get("/states", response_model=List[SkillStateResponse], summary="User skill states")
def get_user_skill_states(
    user_id: Annotated[str, Query(description="User UUID")],
    state_filter: Optional[str] = Query(None, description="Filter by state: locked, discovered, unlocked_hidden, activated"),
    include_hidden: bool = Query(False, description="Include locked and unlocked_hidden skills"),
    db: Session = Depends(get_db),
) -> List[SkillStateResponse]:
    """
    Return skill states for a user.

    By default only discovered and activated skills are returned (visible in UI).
    Pass include_hidden=true to include locked and unlocked_hidden skills.
    """
    unlock_service = SkillUnlockService(db)

    # Ensure every hierarchy skill has a state row so this endpoint returns
    # complete user state coverage, not only previously touched rows.
    for source_id in unlock_service.hierarchy:
        unlock_service.get_or_create_skill_state(user_id, source_id)

    states = db.query(UserSkillState).filter(UserSkillState.user_id == user_id).all()

    if state_filter:
        states = [s for s in states if s.state == state_filter]
    if not include_hidden:
        visible = {SkillState.DISCOVERED, SkillState.ACTIVATED}
        states = [s for s in states if s.state in visible]

    # Build global_id → source_skill_id reverse map from hierarchy
    hierarchy = unlock_service.hierarchy
    # Populate the global_id cache for all hierarchy skills (batch)
    global_id_to_source: dict[str, str] = {}
    for source_id in hierarchy:
        gid = unlock_service._resolve_global_id(source_id)
        if gid:
            global_id_to_source[gid] = source_id

    # Build global_id → Skill map
    global_id_to_skill: dict[str, Skill] = {
        s.global_skill_id: s
        for s in db.query(Skill).filter(
            Skill.user_id == user_id,
            Skill.global_skill_id.isnot(None),
        ).all()
    }

    result = []
    for state in states:
        source_id = global_id_to_source.get(state.skill_id)
        if not source_id:
            continue
        skill_info = hierarchy[source_id]
        skill = global_id_to_skill.get(state.skill_id)
        result.append(
            SkillStateResponse(
                skill_id=source_id,
                canonical_name=skill_info["canonical_name"],
                hierarchy_level=skill_info["hierarchy_level"],
                state=state.state,
                user_blocked=state.user_blocked,
                parent_skill_ids=skill_info.get("parent_skill_ids", []),
                discovered_at=state.discovered_at.isoformat() if state.discovered_at else None,
                unlocked_at=state.unlocked_at.isoformat() if state.unlocked_at else None,
                activated_at=state.activated_at.isoformat() if state.activated_at else None,
                total_xp=int(skill.xp) if skill else 0,
                current_level=effective_level_from_xp(int(skill.xp) if skill else 0),
                rank=effective_rank_from_xp(int(skill.xp) if skill else 0),
            )
        )
    return result


@router.post("/evaluate-all", summary="Batch-evaluate all skill unlock states")
def evaluate_all_skills(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> dict:
    """Walk every hierarchy skill, apply pending transitions, and report changes."""
    unlock_service = SkillUnlockService(db)
    transitions = unlock_service.evaluate_all_skills(user_id)
    return {"transitions_count": len(transitions), "transitions": transitions}


@router.get("", response_model=list[SkillResponse], summary="List user skills")
def list_skills(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> list[SkillResponse]:
    user_exists = db.query(User.id).filter(User.id == user_id).first()
    if user_exists is None:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found.")

    skills = (
        db.query(Skill, GlobalSkill.category)
        .outerjoin(GlobalSkill, Skill.global_skill_id == GlobalSkill.id)
        .filter(Skill.user_id == user_id)
        .order_by(Skill.xp.desc(), Skill.name.asc())
        .all()
    )

    return [
        _skill_to_response(skill, category or "Growth") for skill, category in skills
    ]


@router.get("/{skill_id}", response_model=SkillResponse, summary="Get one skill")
def get_skill(
    skill_id: str,
    user_id: Annotated[str, Query(description="Owner user UUID")],
    db: Session = Depends(get_db),
) -> SkillResponse:
    row = (
        db.query(Skill, GlobalSkill.category)
        .outerjoin(GlobalSkill, Skill.global_skill_id == GlobalSkill.id)
        .filter(Skill.id == skill_id, Skill.user_id == user_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id!r} not found.")

    skill, category = row
    return _skill_to_response(skill, category or "Growth")


@router.get("/{skill_id}/unlock-info", response_model=UnlockInfoResponse, summary="Unlock requirements for a skill")
def get_skill_unlock_info(
    skill_id: str,
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> UnlockInfoResponse:
    """
    Return detailed unlock status for a hierarchy skill.

    skill_id here is the source_skill_id (e.g. "skill_physical_running"),
    not the user Skill UUID.
    """
    unlock_service = SkillUnlockService(db)
    canonical_skill_id = unlock_service.normalize_source_skill_id(skill_id) or skill_id
    info = unlock_service.get_unlock_info(user_id, canonical_skill_id)
    if not info:
        raise HTTPException(
            status_code=404,
            detail=f"Skill {canonical_skill_id!r} not found in hierarchy.",
        )
    return UnlockInfoResponse(**info)


@router.post("/{skill_id}/block", summary="Toggle skill blocking")
def toggle_skill_blocking(
    skill_id: str,
    request: BlockSkillRequest,
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> dict:
    """
    Set user_blocked on a hierarchy skill.

    skill_id is the source_skill_id. Fails if the user's Skill record is at Lv20+.
    """
    unlock_service = SkillUnlockService(db)
    canonical_skill_id = unlock_service.normalize_source_skill_id(skill_id)

    if canonical_skill_id is None or canonical_skill_id not in unlock_service.hierarchy:
        raise HTTPException(
            status_code=404,
            detail=f"Skill {skill_id!r} not found in hierarchy.",
        )

    global_id = unlock_service._resolve_global_id(canonical_skill_id)
    if global_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"Skill {canonical_skill_id!r} has no global KB entry.",
        )

    skill = (
        db.query(Skill)
        .filter(Skill.user_id == user_id, Skill.global_skill_id == global_id)
        .first()
    )
    if skill and skill.level >= 20:
        raise HTTPException(
            status_code=400,
            detail="Cannot block/unblock a skill at Level 20 or higher.",
        )

    state = unlock_service.get_or_create_skill_state(user_id, canonical_skill_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Could not resolve state for skill {canonical_skill_id!r}.",
        )

    state.user_blocked = request.blocked
    db.commit()

    return {
        "skill_id": canonical_skill_id,
        "user_blocked": state.user_blocked,
        "message": f"Skill {'blocked' if request.blocked else 'unblocked'} successfully.",
    }
