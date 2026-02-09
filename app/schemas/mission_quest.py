"""
Mission/Quest Pydantic schemas for Status Window API.

This module defines schemas for Mission/Quest data validation and serialization:
- MQTemplateBase/Create/Response: For MissionQuestTemplate (global template bank)
- UserMQBase/Create/Update/Response: For UserMissionQuest (user-specific instances)

Missions/Quests support hierarchical structure, multiple completion types,
and XP/coin rewards.
"""
from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.base import BaseSchema, DescriptionStr, NameStr, UUIDStr


# =============================================================================
# MISSION/QUEST TEMPLATE SCHEMAS
# =============================================================================


class MQTemplateBase(BaseSchema):
    """
    Base schema with shared MissionQuestTemplate fields.

    Used as a parent class for MQTemplateCreate and MQTemplateResponse.
    Defines the template's core properties.

    Attributes:
        name: Template name (1-100 characters)
        description_template: Template with {user_name} placeholders
        type: Quest type (daily, timed, periodic, repeatable, etc.)
        structure: Quest structure (single_action, multi_action, multi_part)
        completion_condition: JSON defining completion logic
        reward_xp: XP awarded on completion
        reward_coins: Coins awarded on completion
        difficulty: Difficulty level (easy, medium, hard, etc.)
        category: Category for organization
    """

    name: NameStr
    description_template: str = Field(max_length=1000)
    type: str = Field(max_length=50)
    structure: str = Field(max_length=50)
    autostart: bool = Field(default=False)
    completion_condition: dict = Field(default_factory=dict)
    reward_xp: int = Field(default=0, ge=0)
    reward_coins: int = Field(default=0, ge=0)
    difficulty: str = Field(default="medium", max_length=20)
    category: str | None = Field(default=None, max_length=50)


class MQTemplateCreate(MQTemplateBase):
    """
    Schema for creating a new MissionQuestTemplate.

    Used for POST /mq-templates endpoint. Inherits all fields
    from MQTemplateBase with no additional fields.

    Example:
        {
            "name": "Morning Meditation",
            "description_template": "Complete a {duration} meditation",
            "type": "daily",
            "structure": "single_action",
            "completion_condition": {"type": "yes_no"},
            "reward_xp": 25,
            "reward_coins": 10,
            "difficulty": "easy",
            "category": "Health"
        }
    """

    pass


class MQTemplateResponse(MQTemplateBase):
    """
    Schema for MissionQuestTemplate API responses.

    Includes all template fields returned by the API,
    including the auto-generated id.

    Attributes:
        id: Unique UUID identifier

    Example:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "name": "Morning Meditation",
            "description_template": "Complete a {duration} meditation",
            "type": "daily",
            "structure": "single_action",
            "completion_condition": {"type": "yes_no"},
            "reward_xp": 25,
            "reward_coins": 10,
            "difficulty": "easy",
            "category": "Health"
        }
    """

    id: UUIDStr

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# USER MISSION/QUEST SCHEMAS
# =============================================================================


class UserMQBase(BaseSchema):
    """
    Base schema with shared UserMissionQuest fields.

    Used as a parent class for UserMQCreate and UserMQResponse.
    Contains core fields for user-specific quest instances.

    Attributes:
        name: Quest name (1-100 characters)
        personalized_description: AI-generated description for this user
        status: Current status (not_started, in_progress, completed, failed)
        completion_target: Target value for completion (default 100)
        deadline: Optional deadline for timed quests
    """

    name: NameStr
    personalized_description: DescriptionStr = None
    status: str = Field(default="not_started", max_length=20)
    autostart: bool = Field(default=False)
    completion_target: int = Field(default=100, ge=0)
    deadline: datetime | None = None


class UserMQCreate(UserMQBase):
    """
    Schema for creating a new UserMissionQuest.

    Used for POST /user-mq endpoint. Inherits base fields and
    requires user_id for ownership. Optional template_id and
    parent_mq_id for template-based and hierarchical quests.

    Attributes:
        user_id: UUID of the user who owns this quest
        template_id: Optional reference to MissionQuestTemplate
        parent_mq_id: Optional parent quest for hierarchy

    Example:
        {
            "name": "Complete morning routine",
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "template_id": "987fcdeb-51a2-3bc4-d567-890123456789",
            "status": "not_started",
            "completion_target": 100
        }
    """

    user_id: UUIDStr
    template_id: UUIDStr | None = None
    parent_mq_id: UUIDStr | None = None
    autostart: bool | None = None


class UserMQUpdate(BaseSchema):
    """
    Schema for partial UserMissionQuest updates.

    Used for PATCH /user-mq/{id} endpoint. All fields are optional
    to allow partial updates of quest attributes.

    Attributes:
        status: Optional new status
        completion_progress: Optional new progress value

    Example:
        {
            "status": "in_progress",
            "completion_progress": 50
        }
    """

    status: str | None = Field(default=None, max_length=20)
    completion_progress: int | None = Field(default=None, ge=0)


class UserMQResponse(UserMQBase):
    """
    Schema for UserMissionQuest API responses.

    Includes all quest fields returned by the API, including
    auto-generated fields like id and timestamps.

    Attributes:
        id: Unique UUID identifier
        user_id: UUID of the owning user
        template_id: Reference to template (if template-based)
        parent_mq_id: Parent quest ID (if hierarchical)
        completion_progress: Current progress value
        created_at: When the quest was created
        completed_at: When the quest was completed (if applicable)

    Example:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "user_id": "987fcdeb-51a2-3bc4-d567-890123456789",
            "name": "Complete morning routine",
            "personalized_description": "Start your day right!",
            "status": "in_progress",
            "completion_progress": 50,
            "completion_target": 100,
            "template_id": null,
            "parent_mq_id": null,
            "deadline": null,
            "created_at": "2025-01-15T10:30:00",
            "completed_at": null
        }
    """

    id: UUIDStr
    user_id: UUIDStr
    template_id: UUIDStr | None
    parent_mq_id: UUIDStr | None
    completion_progress: int
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
