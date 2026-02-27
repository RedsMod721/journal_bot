"""
CRUD operations for UserStats model.

This module provides database operations for UserStats management:
- Create: Create new user stats
- Read: Get stats by user ID
- Update: Modify stats, adjust individual stats, reset to defaults

All functions take a SQLAlchemy Session as the first argument
and return UserStats model instances or None for not-found cases.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.user_stats import UserStats
from app.schemas.user_stats import UserStatsCreate, UserStatsUpdate

# Default values for stats reset
DEFAULT_STATS = {
    "hp": 100,
    "mp": 100,
    "mental_health": 70,
    "physical_health": 70,
    "relationship_quality": 50,
    "socialization_level": 50,
}


def create_user_stats(db: Session, stats: UserStatsCreate) -> UserStats:
    """
    Create new user stats in the database.

    Args:
        db: Database session
        stats: UserStatsCreate schema with user_id and optional stat values

    Returns:
        UserStats: The created stats instance

    Example:
        stats_data = UserStatsCreate(user_id="123e4567-...")
        stats = create_user_stats(db, stats_data)
    """
    db_stats = UserStats(
        user_id=stats.user_id,
        hp=stats.hp,
        mp=stats.mp,
        mental_health=stats.mental_health,
        physical_health=stats.physical_health,
        relationship_quality=stats.relationship_quality,
        socialization_level=stats.socialization_level,
    )
    db.add(db_stats)
    db.commit()
    db.refresh(db_stats)
    return db_stats


def get_user_stats(db: Session, user_id: str) -> UserStats | None:
    """
    Retrieve user stats by user ID.

    Args:
        db: Database session
        user_id: The UUID string of the user

    Returns:
        UserStats: The stats instance if found
        None: If no stats exist for that user
    """
    return db.query(UserStats).filter(UserStats.user_id == user_id).first()


def update_user_stats(
    db: Session, user_id: str, stats_update: UserStatsUpdate
) -> UserStats | None:
    """
    Update user stats attributes.

    Only updates fields that are explicitly set in the update schema.
    Uses exclude_unset=True to allow partial updates. Also updates
    the updated_at timestamp.

    Args:
        db: Database session
        user_id: The UUID string of the user
        stats_update: UserStatsUpdate schema with fields to update

    Returns:
        UserStats: The updated stats instance
        None: If no stats exist for that user

    Example:
        update = UserStatsUpdate(hp=85, mp=90)
        stats = update_user_stats(db, user_id, update)
    """
    db_stats = db.query(UserStats).filter(UserStats.user_id == user_id).first()
    if db_stats is None:
        return None

    update_data = stats_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_stats, field, value)

    db_stats.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_stats)
    return db_stats


def adjust_stat(
    db: Session, user_id: str, stat_name: str, delta: int
) -> UserStats | None:
    """
    Adjust a specific stat by a delta value.

    Adds the delta to the current stat value and clamps the result
    to the 0-100 range. Updates the updated_at timestamp.

    Args:
        db: Database session
        user_id: The UUID string of the user
        stat_name: Name of the stat to adjust (hp, mp, mental_health, etc.)
        delta: Amount to add (positive) or subtract (negative)

    Returns:
        UserStats: The updated stats instance
        None: If no stats exist for that user or invalid stat_name

    Example:
        # Reduce HP by 10
        stats = adjust_stat(db, user_id, "hp", -10)

        # Increase mental_health by 5
        stats = adjust_stat(db, user_id, "mental_health", 5)
    """
    db_stats = db.query(UserStats).filter(UserStats.user_id == user_id).first()
    if db_stats is None:
        return None

    # Validate stat_name exists on the model
    if not hasattr(db_stats, stat_name) or stat_name not in DEFAULT_STATS:
        return None

    current_value = getattr(db_stats, stat_name)
    new_value = max(0, min(100, current_value + delta))
    setattr(db_stats, stat_name, new_value)

    db_stats.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_stats)
    return db_stats


def reset_user_stats(db: Session, user_id: str) -> UserStats | None:
    """
    Reset all user stats to default values.

    Resets: hp=100, mp=100, mental_health=70, physical_health=70,
    relationship_quality=50, socialization_level=50.
    Also updates the updated_at timestamp.

    Args:
        db: Database session
        user_id: The UUID string of the user

    Returns:
        UserStats: The reset stats instance
        None: If no stats exist for that user
    """
    db_stats = db.query(UserStats).filter(UserStats.user_id == user_id).first()
    if db_stats is None:
        return None

    for stat_name, default_value in DEFAULT_STATS.items():
        setattr(db_stats, stat_name, default_value)

    db_stats.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_stats)
    return db_stats
