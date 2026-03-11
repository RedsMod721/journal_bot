"""User-related API endpoints used by the Week 4 UI/CLI."""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.core.realm import (
    RealmRankWordingPreset,
    list_rank_wording_presets,
    normalize_realm_preferences,
    normalize_user_preferences,
)
from src.core.skill_unlocks import SkillUnlockService
from src.core.themes import ensure_user_themes
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    """Request body for creating a new user."""

    email: Optional[str] = Field(None, description="Unique e-mail address (auto-generated placeholder if omitted)")
    password: str = Field(..., min_length=8, description="Plain-text password (hashed server-side)")
    username: Optional[str] = Field(None, max_length=50)
    display_name: Optional[str] = Field(None, max_length=100)
    timezone: str = Field("UTC", description="IANA timezone string")
    home_country: str = Field("FR", min_length=2, max_length=2, description="ISO 3166-1 alpha-2")


class UserListItem(BaseModel):
    id: str
    username: str | None
    display_name: str | None
    email: str | None


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


class RealmScopePreferences(BaseModel):
    visual: bool = True
    naming: bool = False
    messages: bool = False
    llm: bool = False


class RealmRanksWordingPreference(BaseModel):
    preset: RealmRankWordingPreset = RealmRankWordingPreset.STANDARD


class RealmPreferences(BaseModel):
    scope: RealmScopePreferences = Field(default_factory=RealmScopePreferences)
    ranks_wording: RealmRanksWordingPreference = Field(
        default_factory=RealmRanksWordingPreference
    )


class SkillHierarchyPreferences(BaseModel):
    default_blocked_preference: bool = False


class UserPreferencesResponse(BaseModel):
    user_id: str
    realm: RealmPreferences
    skill_hierarchy: SkillHierarchyPreferences


class UserPreferencesUpdateRequest(BaseModel):
    realm: Optional[RealmPreferences] = None
    skill_hierarchy: Optional[SkillHierarchyPreferences] = None


class RankWordingOption(BaseModel):
    rank: str
    wording: str


class RankWordingPresetResponse(BaseModel):
    preset: RealmRankWordingPreset
    name: str
    ranks: list[RankWordingOption]


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


def _load_user_or_404(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id!r} not found.")
    return user


def _serialize_user_preferences(
    *, user_id: str, preferences: dict[str, Any], default_blocked_preference: bool
) -> UserPreferencesResponse:
    return UserPreferencesResponse(
        user_id=user_id,
        realm=RealmPreferences.model_validate(preferences["realm"]),
        skill_hierarchy=SkillHierarchyPreferences(
            default_blocked_preference=default_blocked_preference
        ),
    )


@router.post(
    "",
    response_model=UserListItem,
    status_code=201,
    summary="Create a new user",
    responses={
        201: {"description": "User created; L1 skills + canonical themes initialized"},
        409: {"description": "E-mail already registered"},
    },
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
) -> UserListItem:
    """
    Create a new user account and initialize L1 skills + canonical themes.

    L1 skills (top-level categories in the global hierarchy) are created in
    ACTIVATED state immediately so the user can start earning XP from their
    first journal entry.

    ``email`` is optional.  When omitted a UUID-based placeholder is stored;
    the user can update it later.

    Password storage
    ----------------
    The plain-text password is SHA-256 hashed before storage.  Replace with
    bcrypt/argon2 when adding production auth.
    """
    import uuid as _uuid

    # Resolve email — generate placeholder if not supplied
    email = payload.email or f"user_{_uuid.uuid4().hex[:12]}@placeholder.local"

    # Conflict check (only meaningful when a real email is provided)
    existing = db.query(User.id).filter(User.email == email).first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"E-mail {email!r} is already registered.",
        )

    password_hash = hashlib.sha256(payload.password.encode()).hexdigest()

    user = User(
        email=email,
        password_hash=password_hash,
        username=payload.username,
        display_name=payload.display_name,
        timezone=payload.timezone,
        home_country=payload.home_country.upper(),
    )
    db.add(user)
    db.flush()  # populate user.id before L1 init

    # Initialize L1 skills + canonical themes (idempotent — safe on retry)
    try:
        unlock_service = SkillUnlockService(db)
        unlock_service.initialize_user_skills(user.id)
        ensure_user_themes(db, user.id)
        logger.info("Initialized L1 skills and canonical themes for new user %s.", user.id)
    except Exception:
        logger.warning(
            "Could not initialize L1 skills/themes for user %s — hierarchy data may "
            "not yet be seeded.",
            user.id,
            exc_info=True,
        )

    db.commit()

    return UserListItem(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
    )


@router.get("", response_model=list[UserListItem], summary="List users (dev helper)")
def list_users(
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Max results")] = 20,
    db: Session = Depends(get_db),
) -> list[UserListItem]:
    users = (
        db.query(User.id, User.username, User.display_name, User.email)
        .order_by(User.created_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
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
    "/preferences/realm/rank-wording-presets",
    response_model=list[RankWordingPresetResponse],
    summary="List available realm rank-wording presets",
)
def get_realm_rank_wording_presets() -> list[RankWordingPresetResponse]:
    presets = list_rank_wording_presets()
    return [
        RankWordingPresetResponse(
            preset=RealmRankWordingPreset(str(item["preset"])),
            name=str(item["name"]),
            ranks=[
                RankWordingOption(rank=str(row["rank"]), wording=str(row["wording"]))
                for row in item["ranks"]
            ],
        )
        for item in presets
    ]


@router.get(
    "/{user_id}/preferences",
    response_model=UserPreferencesResponse,
    summary="Get user preferences",
)
def get_user_preferences(
    user_id: str,
    db: Session = Depends(get_db),
) -> UserPreferencesResponse:
    user = _load_user_or_404(db, user_id)
    normalized = normalize_user_preferences(user.user_preferences)
    if user.user_preferences != normalized:
        user.user_preferences = normalized
        db.flush()
    return _serialize_user_preferences(
        user_id=user.id,
        preferences=normalized,
        default_blocked_preference=user.default_blocked_preference,
    )


@router.put(
    "/{user_id}/preferences",
    response_model=UserPreferencesResponse,
    summary="Update user preferences",
)
def update_user_preferences(
    user_id: str,
    payload: UserPreferencesUpdateRequest,
    db: Session = Depends(get_db),
) -> UserPreferencesResponse:
    user = _load_user_or_404(db, user_id)
    normalized = normalize_user_preferences(user.user_preferences)
    if payload.realm is not None:
        normalized["realm"] = normalize_realm_preferences(
            payload.realm.model_dump(mode="python")
        )
    if payload.skill_hierarchy is not None:
        user.default_blocked_preference = (
            payload.skill_hierarchy.default_blocked_preference
        )
    user.user_preferences = normalized
    db.flush()
    return _serialize_user_preferences(
        user_id=user.id,
        preferences=normalized,
        default_blocked_preference=user.default_blocked_preference,
    )


@router.get(
    "/{user_id}/stats",
    response_model=UserStatsResponse,
    summary="Get aggregate RPG stats for a user",
)
def get_user_stats(user_id: str, db: Session = Depends(get_db)) -> UserStatsResponse:
    _load_user_or_404(db, user_id)

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
