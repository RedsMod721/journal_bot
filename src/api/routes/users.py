"""User-related API endpoints used by the Week 4 UI/CLI."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.core.xp import (
    calculate_user_level_from_xp,
    calculate_user_xp_for_level,
)
from src.db.models.journal_entry import JournalEntry
from src.db.models.quest import Quest
from src.db.models.skill import Skill
from src.db.models.user import User
from src.db.models.xp import XpAward
from src.db.session import get_db

router = APIRouter(prefix="/users", tags=["users"])


class UserListItem(BaseModel):
    id: str
    username: str | None
    display_name: str | None
    email: str


class UserStatsResponse(BaseModel):
    user_id: str
    total_xp: int
    current_level: int
    current_level_xp: int
    next_level_xp: int
    active_quests: int
    skills_practiced: int
    journal_entries: int
    current_streak: int
    xp_today: int
    xp_this_week: int
    recent_gain: int


def _calculate_streak(entry_dates: list[date]) -> int:
    """Calculate consecutive-day streak up to today (UTC)."""
    if not entry_dates:
        return 0

    unique_dates = sorted(set(entry_dates), reverse=True)
    today = datetime.now(timezone.utc).date()

    # Streak may start today or yesterday.
    if unique_dates[0] == today:
        expected = today
    elif unique_dates[0] == today - timedelta(days=1):
        expected = today - timedelta(days=1)
    else:
        return 0

    streak = 0
    for entry_day in unique_dates:
        if entry_day == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif entry_day < expected:
            break
    return streak


@router.get("", response_model=list[UserListItem], summary="List users (dev helper)")
def list_users(
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Max results")] = 20,
    db: Session = Depends(get_db),
) -> list[UserListItem]:
    users = (
        db.query(User).order_by(User.created_at.asc()).offset(skip).limit(limit).all()
    )
    return [
        UserListItem(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            email=u.email,
        )
        for u in users
    ]


@router.get(
    "/{user_id}/stats",
    response_model=UserStatsResponse,
    summary="Get aggregate RPG stats for a user",
)
def get_user_stats(user_id: str, db: Session = Depends(get_db)) -> UserStatsResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found.")

    total_xp = int(
        db.query(func.coalesce(func.sum(XpAward.amount), 0))
        .filter(XpAward.user_id == user_id)
        .scalar()
        or 0
    )
    if total_xp == 0:
        # Fallback for environments where historical XP awards were not backfilled.
        total_xp = int(
            db.query(func.coalesce(func.sum(Skill.xp), 0))
            .filter(Skill.user_id == user_id)
            .scalar()
            or 0
        )

    current_level = calculate_user_level_from_xp(total_xp)
    current_level_floor = calculate_user_xp_for_level(current_level)
    next_level_floor = calculate_user_xp_for_level(current_level + 1)

    active_quests = int(
        db.query(func.count(Quest.id))
        .filter(Quest.user_id == user_id, Quest.status == "active")
        .scalar()
        or 0
    )
    skills_practiced = int(
        db.query(func.count(Skill.id))
        .filter(Skill.user_id == user_id, Skill.xp > 0)
        .scalar()
        or 0
    )
    journal_entries = int(
        db.query(func.count(JournalEntry.id))
        .filter(JournalEntry.user_id == user_id)
        .scalar()
        or 0
    )

    entry_dates_raw = (
        db.query(JournalEntry.created_at)
        .filter(JournalEntry.user_id == user_id)
        .order_by(JournalEntry.created_at.desc())
        .all()
    )
    entry_dates = [
        ts.astimezone(timezone.utc).date()
        for (ts,) in entry_dates_raw
        if isinstance(ts, datetime)
    ]
    current_streak = _calculate_streak(entry_dates)

    now_utc = datetime.now(timezone.utc)
    start_today = datetime.combine(now_utc.date(), time.min, tzinfo=timezone.utc)
    start_week = start_today - timedelta(days=start_today.weekday())

    xp_today = int(
        db.query(func.coalesce(func.sum(XpAward.amount), 0))
        .filter(XpAward.user_id == user_id, XpAward.awarded_at >= start_today)
        .scalar()
        or 0
    )
    xp_this_week = int(
        db.query(func.coalesce(func.sum(XpAward.amount), 0))
        .filter(XpAward.user_id == user_id, XpAward.awarded_at >= start_week)
        .scalar()
        or 0
    )

    latest_completed_entry = (
        db.query(JournalEntry.id)
        .filter(JournalEntry.user_id == user_id, JournalEntry.status == "completed")
        .order_by(
            func.coalesce(JournalEntry.processed_at, JournalEntry.created_at).desc()
        )
        .first()
    )
    if latest_completed_entry is None:
        recent_gain = 0
    else:
        latest_entry_id = latest_completed_entry[0]
        recent_gain = int(
            db.query(func.coalesce(func.sum(XpAward.amount), 0))
            .filter(XpAward.user_id == user_id, XpAward.entry_id == latest_entry_id)
            .scalar()
            or 0
        )

    return UserStatsResponse(
        user_id=user_id,
        total_xp=total_xp,
        current_level=current_level,
        current_level_xp=max(0, total_xp - current_level_floor),
        next_level_xp=max(1, next_level_floor - current_level_floor),
        active_quests=active_quests,
        skills_practiced=skills_practiced,
        journal_entries=journal_entries,
        current_streak=current_streak,
        xp_today=xp_today,
        xp_this_week=xp_this_week,
        recent_gain=recent_gain,
    )
