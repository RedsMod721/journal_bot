"""
Skill Pydantic schemas for Status Window API.

This module defines schemas for Skill data validation and serialization:
- SkillBase: Shared fields for skill data
- SkillCreate: Schema for creating new skills (POST requests)
- SkillUpdate: Schema for partial skill updates (PATCH requests)
- SkillResponse: Schema for API responses with full skill data

All schemas use the base types defined in app.schemas.base for consistency.
"""
from pydantic import ConfigDict, Field

from app.schemas.base import (
    BaseSchema,
    DescriptionStr,
    LevelInt,
    NameStr,
    UUIDStr,
    XPFloat,
)


class SkillBase(BaseSchema):
    """
    Base schema with shared skill fields.

    Used as a parent class for SkillCreate and SkillResponse.
    Contains core fields that define a skill's identity.

    Attributes:
        name: Skill name (1-100 characters)
        description: Optional skill description (up to 500 characters)
        difficulty: Skill difficulty rating (default "Medium")
        parent_skill_id: Optional parent skill for skill trees
    """

    name: NameStr
    description: DescriptionStr = None
    difficulty: str = "Medium"
    parent_skill_id: str | None = None


class SkillCreate(SkillBase):
    """
    Schema for creating a new skill.

    Used for POST /skills endpoint. Inherits name, description,
    difficulty, and parent_skill_id from SkillBase.
    Requires user_id for ownership, optional theme_id for categorization.

    Attributes:
        user_id: UUID of the user who owns this skill
        theme_id: Optional UUID of the theme this skill belongs to

    Example:
        {
            "name": "Python Programming",
            "description": "Learning Python language",
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "theme_id": "987fcdeb-51a2-3bc4-d567-890123456789",
            "difficulty": "Hard"
        }
    """

    user_id: UUIDStr
    theme_id: str | None = None


class SkillUpdate(BaseSchema):
    """
    Schema for partial skill updates.

    Used for PATCH /skills/{id} endpoint. All fields are optional
    to allow partial updates of skill attributes.

    Attributes:
        name: Optional new skill name
        description: Optional new description
        difficulty: Optional new difficulty rating

    Example:
        {
            "name": "Advanced Python",
            "difficulty": "Expert"
        }
    """

    name: NameStr | None = None
    description: DescriptionStr = None
    difficulty: str | None = None


class SkillResponse(SkillBase):
    """
    Schema for skill API responses.

    Includes all skill fields returned by the API, including
    auto-generated fields like id and computed values like level.

    Attributes:
        id: Unique UUID identifier
        user_id: UUID of the owning user
        theme_id: Optional UUID of the parent theme
        level: Current level (starts at 0)
        xp: Current XP towards next level
        xp_to_next_level: XP required for next level-up
        rank: Current rank (Beginner -> Master)
        practice_time_minutes: Total practice time accumulated
        metadata: JSON field for extensibility

    Example:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "user_id": "987fcdeb-51a2-3bc4-d567-890123456789",
            "name": "Python Programming",
            "description": "Learning Python language",
            "difficulty": "Hard",
            "parent_skill_id": null,
            "theme_id": null,
            "level": 10,
            "xp": 75.0,
            "xp_to_next_level": 309.59,
            "rank": "Amateur",
            "practice_time_minutes": 1200,
            "metadata": {}
        }
    """

    id: UUIDStr
    user_id: UUIDStr
    theme_id: str | None
    level: LevelInt
    xp: XPFloat
    xp_to_next_level: XPFloat
    rank: str
    practice_time_minutes: int = Field(ge=0)
    metadata: dict = Field(default_factory=dict, validation_alias="skill_metadata")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
