"""
Theme Pydantic schemas for Status Window API.

This module defines schemas for Theme data validation and serialization:
- ThemeBase: Shared fields for theme data
- ThemeCreate: Schema for creating new themes (POST requests)
- ThemeUpdate: Schema for partial theme updates (PATCH requests)
- ThemeResponse: Schema for API responses with full theme data

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


class ThemeBase(BaseSchema):
    """
    Base schema with shared theme fields.

    Used as a parent class for ThemeCreate and ThemeResponse.
    Contains core fields that define a theme's identity.

    Attributes:
        name: Theme name (1-100 characters)
        description: Optional theme description (up to 500 characters)
        parent_theme_id: Optional parent theme for hierarchy
    """

    name: NameStr
    description: DescriptionStr = None
    parent_theme_id: str | None = None


class ThemeCreate(ThemeBase):
    """
    Schema for creating a new theme.

    Used for POST /themes endpoint. Inherits name, description, and
    parent_theme_id from ThemeBase. Requires user_id for ownership.

    Attributes:
        user_id: UUID of the user who owns this theme

    Example:
        {
            "name": "Physical Health",
            "description": "Fitness and wellness goals",
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "parent_theme_id": null
        }
    """

    user_id: UUIDStr


class ThemeUpdate(BaseSchema):
    """
    Schema for partial theme updates.

    Used for PATCH /themes/{id} endpoint. All fields are optional
    to allow partial updates of theme attributes.

    Attributes:
        name: Optional new theme name
        description: Optional new description

    Example:
        {
            "name": "Updated Theme Name"
        }
    """

    name: NameStr | None = None
    description: DescriptionStr = None


class ThemeResponse(ThemeBase):
    """
    Schema for theme API responses.

    Includes all theme fields returned by the API, including
    auto-generated fields like id and computed values like level.

    Attributes:
        id: Unique UUID identifier
        user_id: UUID of the owning user
        level: Current level (starts at 0)
        xp: Current XP towards next level
        xp_to_next_level: XP required for next level-up
        corrosion_level: Degradation status if neglected
        metadata: JSON field for extensibility

    Example:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "user_id": "987fcdeb-51a2-3bc4-d567-890123456789",
            "name": "Physical Health",
            "description": "Fitness and wellness goals",
            "parent_theme_id": null,
            "level": 5,
            "xp": 45.0,
            "xp_to_next_level": 201.14,
            "corrosion_level": "Fresh",
            "metadata": {}
        }
    """

    id: UUIDStr
    user_id: UUIDStr
    level: LevelInt
    xp: XPFloat
    xp_to_next_level: XPFloat
    corrosion_level: str
    metadata: dict = Field(default_factory=dict, validation_alias="theme_metadata")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
