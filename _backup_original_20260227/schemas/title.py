"""
Title Pydantic schemas for Status Window API.

This module defines schemas for both Title models:

TitleTemplate (Global Bank):
- TitleTemplateBase: Shared fields for title template data
- TitleTemplateCreate: Schema for creating new title templates
- TitleTemplateResponse: Schema for API responses

UserTitle (User Instances):
- UserTitleBase: Shared fields for user title data
- UserTitleCreate: Schema for awarding titles to users
- UserTitleResponse: Schema for API responses

All schemas use the base types defined in app.schemas.base for consistency.
"""
from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.base import (
    BaseSchema,
    NameStr,
    UUIDStr,
)


# =============================================================================
# TITLE TEMPLATE SCHEMAS (Global Bank)
# =============================================================================


class TitleTemplateBase(BaseSchema):
    """
    Base schema with shared title template fields.

    Used as a parent class for TitleTemplateCreate and TitleTemplateResponse.
    Contains core fields that define a title's identity and effects.

    Attributes:
        name: Title name (1-100 characters)
        description_template: Template with {user_name} placeholders
        effect: JSON containing buff/debuff effects
        rank: Title rank (F, E, D, C, B, A, S)
        unlock_condition: JSON defining how to unlock this title
        category: Optional category for organization
        is_hidden: Whether unlock conditions are hidden until earned
    """

    name: NameStr
    description_template: str
    effect: dict = Field(default_factory=dict)
    rank: str = "D"
    unlock_condition: dict = Field(default_factory=dict)
    category: str | None = None
    is_hidden: bool = False


class TitleTemplateCreate(TitleTemplateBase):
    """
    Schema for creating a new title template.

    Used for POST /title-templates endpoint. Inherits all fields
    from TitleTemplateBase.

    Example:
        {
            "name": "Early Riser",
            "description_template": "{user_name} wakes before the sun",
            "effect": {"type": "xp_multiplier", "value": 1.05},
            "rank": "C",
            "unlock_condition": {"type": "morning_entries", "count": 10},
            "category": "Productivity",
            "is_hidden": false
        }
    """

    pass


class TitleTemplateResponse(TitleTemplateBase):
    """
    Schema for title template API responses.

    Includes all title template fields returned by the API.

    Attributes:
        id: Unique UUID identifier

    Example:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "name": "Early Riser",
            "description_template": "{user_name} wakes before the sun",
            "effect": {"type": "xp_multiplier", "value": 1.05},
            "rank": "C",
            "unlock_condition": {"type": "morning_entries", "count": 10},
            "category": "Productivity",
            "is_hidden": false
        }
    """

    id: UUIDStr

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# USER TITLE SCHEMAS (User Instances)
# =============================================================================


class UserTitleBase(BaseSchema):
    """
    Base schema with shared user title fields.

    Used as a parent class for UserTitleCreate and UserTitleResponse.
    Contains fields for user-specific title instances.

    Attributes:
        title_template_id: UUID of the title template
        is_equipped: Whether the title's effects are active
        personalized_description: AI-generated description for this user
        expires_at: When the title expires (None for permanent)
    """

    title_template_id: UUIDStr
    is_equipped: bool = True
    personalized_description: str | None = None
    expires_at: datetime | None = None


class UserTitleCreate(UserTitleBase):
    """
    Schema for awarding a title to a user.

    Used for POST /user-titles endpoint. Inherits all fields
    from UserTitleBase and adds user_id.

    Attributes:
        user_id: UUID of the user receiving the title

    Example:
        {
            "user_id": "987fcdeb-51a2-3bc4-d567-890123456789",
            "title_template_id": "123e4567-e89b-12d3-a456-426614174000",
            "is_equipped": true,
            "personalized_description": "Sebastian wakes before the sun"
        }
    """

    user_id: UUIDStr


class UserTitleResponse(UserTitleBase):
    """
    Schema for user title API responses.

    Includes all user title fields returned by the API.

    Attributes:
        id: Unique UUID identifier
        user_id: UUID of the owning user
        acquired_at: When the user earned this title

    Example:
        {
            "id": "abc12345-e89b-12d3-a456-426614174000",
            "user_id": "987fcdeb-51a2-3bc4-d567-890123456789",
            "title_template_id": "123e4567-e89b-12d3-a456-426614174000",
            "is_equipped": true,
            "personalized_description": "Sebastian wakes before the sun",
            "expires_at": null,
            "acquired_at": "2024-01-15T08:30:00Z"
        }
    """

    id: UUIDStr
    user_id: UUIDStr
    acquired_at: datetime

    model_config = ConfigDict(from_attributes=True)
