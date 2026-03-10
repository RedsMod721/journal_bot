"""Skill API endpoints used by the Week 4 UI/CLI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.xp import calculate_level_from_xp, calculate_xp_for_level
from src.db.models.global_kb import GlobalSkill
from src.db.models.skill import Skill
from src.db.models.user import User
from src.db.session import get_db

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillResponse(BaseModel):
    skill_id: str
    user_id: str
    canonical_name: str
    category: str
    total_xp: int
    current_level: int
    current_level_xp: int
    next_level_xp: int
    last_practiced_at: datetime
    created_at: datetime


def _skill_to_response(skill: Skill, category: str) -> SkillResponse:
    last_practiced = skill.last_activity_at or skill.updated_at or skill.created_at
    if last_practiced.tzinfo is None:
        last_practiced = last_practiced.replace(tzinfo=timezone.utc)
    total_xp = int(skill.xp)
    current_level = calculate_level_from_xp(total_xp)
    current_level_floor = calculate_xp_for_level(current_level)
    next_level_floor = calculate_xp_for_level(current_level + 1)

    return SkillResponse(
        skill_id=skill.id,
        user_id=skill.user_id,
        canonical_name=skill.name or skill.canonical_name,
        category=category,
        total_xp=total_xp,
        current_level=current_level,
        current_level_xp=max(0, total_xp - current_level_floor),
        next_level_xp=max(1, next_level_floor - current_level_floor),
        last_practiced_at=last_practiced,
        created_at=skill.created_at,
    )


@router.get("", response_model=list[SkillResponse], summary="List user skills")
def list_skills(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> list[SkillResponse]:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
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
