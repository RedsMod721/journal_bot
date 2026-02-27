"""
UserStats Pydantic schemas for Status Window API.

This module defines schemas for UserStats data validation and serialization:
- UserStatsBase: Shared fields for user stats data
- UserStatsCreate: Schema for creating new stats (POST requests)
- UserStatsUpdate: Schema for partial stats updates (PATCH requests)
- UserStatsResponse: Schema for API responses with full stats data

UserStats represents the status bars (HP, MP, Mental Health, etc.) that
track the user's current state. All stats use 0-100 scale for consistency.
"""
from datetime import datetime

from pydantic import ConfigDict

from app.schemas.base import BaseSchema


class UserStatsBase(BaseSchema):
    """
    Base schema with shared user stats fields.

    Used as a parent class for UserStatsCreate and UserStatsResponse.
    All stats use 0-100 scale for consistency.

    Attributes:
        hp: Hit Points - Physical energy (0-100)
        mp: Mana Points - Mental energy/focus capacity (0-100)
        mental_health: Mood/anxiety/depression level (0-100)
        physical_health: Fitness/nutrition/sleep quality (0-100)
        relationship_quality: Social connection quality (0-100)
        socialization_level: Recent social activity level (0-100)
    """

    hp: int = 100
    mp: int = 100
    mental_health: int = 70
    physical_health: int = 70
    relationship_quality: int = 50
    socialization_level: int = 50


class UserStatsCreate(UserStatsBase):
    """
    Schema for creating new user stats.

    Used for POST /user-stats endpoint. Inherits all stat fields
    from UserStatsBase. Requires user_id for ownership.

    Attributes:
        user_id: UUID of the user who owns these stats

    Example:
        {
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "hp": 100,
            "mp": 100,
            "mental_health": 70,
            "physical_health": 70,
            "relationship_quality": 50,
            "socialization_level": 50
        }
    """

    user_id: str


class UserStatsUpdate(BaseSchema):
    """
    Schema for partial user stats updates.

    Used for PATCH /user-stats/{id} endpoint. All fields are optional
    to allow partial updates of stat attributes.

    Attributes:
        hp: Optional new HP value
        mp: Optional new MP value
        mental_health: Optional new mental health value
        physical_health: Optional new physical health value
        relationship_quality: Optional new relationship quality value
        socialization_level: Optional new socialization level value

    Example:
        {
            "hp": 85,
            "mp": 90
        }
    """

    hp: int | None = None
    mp: int | None = None
    mental_health: int | None = None
    physical_health: int | None = None
    relationship_quality: int | None = None
    socialization_level: int | None = None


class UserStatsResponse(UserStatsBase):
    """
    Schema for user stats API responses.

    Includes all stats fields returned by the API, including
    auto-generated fields like id and updated_at.

    Attributes:
        id: Unique UUID identifier
        user_id: UUID of the owning user
        updated_at: Last time stats were modified

    Example:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "user_id": "987fcdeb-51a2-3bc4-d567-890123456789",
            "hp": 85,
            "mp": 90,
            "mental_health": 70,
            "physical_health": 75,
            "relationship_quality": 60,
            "socialization_level": 55,
            "updated_at": "2025-01-15T10:30:00"
        }
    """

    id: str
    user_id: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
