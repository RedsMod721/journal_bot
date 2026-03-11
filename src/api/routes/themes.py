"""Theme API endpoints for canonical user theme progression."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.core.themes import CANONICAL_THEME_NAMES, ensure_user_themes, theme_sort_key
from src.core.xp import calculate_xp_for_level, effective_level_from_xp, effective_rank_from_xp
from src.db.models.skill import SkillThemeMapping, Theme
from src.db.models.user import User
from src.db.session import get_db

router = APIRouter(prefix="/themes", tags=["themes"])


class ThemeResponse(BaseModel):
    theme_id: str
    user_id: str
    name: str
    description: Optional[str] = None
    rank: Optional[str] = None
    total_xp: int
    current_level: int
    current_level_xp: int
    next_level_xp: int
    related_skills_count: int
    created_at: datetime
    updated_at: datetime


def _to_theme_response(theme: Theme, related_skills_count: int) -> ThemeResponse:
    total_xp = int(theme.xp)
    current_level = effective_level_from_xp(total_xp)
    rank = effective_rank_from_xp(total_xp)

    if current_level <= 0:
        current_level_floor = 0
        next_level_floor = calculate_xp_for_level(2)
    else:
        current_level_floor = calculate_xp_for_level(current_level)
        next_level_floor = calculate_xp_for_level(current_level + 1)

    created_at = theme.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    updated_at = theme.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    return ThemeResponse(
        theme_id=theme.id,
        user_id=theme.user_id,
        name=theme.name,
        description=theme.description,
        rank=rank,
        total_xp=total_xp,
        current_level=current_level,
        current_level_xp=max(0, total_xp - current_level_floor),
        next_level_xp=max(1, next_level_floor - current_level_floor),
        related_skills_count=related_skills_count,
        created_at=created_at,
        updated_at=updated_at,
    )


@router.get("", response_model=list[ThemeResponse], summary="List canonical user themes")
def list_themes(
    user_id: Annotated[str, Query(description="User UUID")],
    db: Session = Depends(get_db),
) -> list[ThemeResponse]:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found.")

    ensure_user_themes(db, user_id)

    themes = (
        db.query(Theme)
        .filter(Theme.user_id == user_id, Theme.name.in_(CANONICAL_THEME_NAMES))
        .all()
    )
    if not themes:
        return []

    related_counts = {
        str(theme_id): int(count)
        for theme_id, count in (
            db.query(
                SkillThemeMapping.theme_id,
                func.count(func.distinct(SkillThemeMapping.skill_id)),
            )
            .filter(SkillThemeMapping.user_id == user_id)
            .group_by(SkillThemeMapping.theme_id)
            .all()
        )
    }

    sorted_themes = sorted(themes, key=lambda row: theme_sort_key(row.name))
    return [
        _to_theme_response(theme, related_counts.get(theme.id, 0))
        for theme in sorted_themes
    ]
