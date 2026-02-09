"""
Mission/Quest models for Status Window API.

This module contains two related models:
1. MissionQuestTemplate - Global M/Q bank (reusable templates)
2. UserMissionQuest - User-specific M/Q instances

Missions/Quests are tasks ranging from daily repeatable actions to multi-stage
story arcs. The template/instance pattern allows element reusability
(cost optimization for AI generation).

Features:
- Hierarchical structure (quests can have child quests)
- Multiple completion types (yes/no, accumulation, quality threshold)
- XP and coin rewards
- Status tracking (not_started, in_progress, completed, failed)
- Progress tracking for accumulation-type quests
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class MissionQuestTemplate(Base):
    """
    Global M/Q bank containing reusable quest/mission templates.

    MissionQuestTemplates are shared across all users and define the M/Q's
    base properties. When a user takes on a quest, a UserMissionQuest instance
    is created referencing this template.

    This pattern supports element reusability - the AI generates templates once,
    and they can be reused with contextual personalization.

    Attributes:
        id: Unique identifier (UUID string)
        name: Quest/mission name (e.g., "Morning Meditation", "30-Day Gym Challenge")
        description_template: Template with {user_name} placeholders
        type: Quest type (daily, timed, periodic, repeatable, etc.)
        structure: Quest structure (single_action, multi_action, multi_part)
        completion_condition: JSON defining completion logic
        reward_xp: XP awarded on completion
        reward_coins: Coins awarded on completion
        difficulty: Difficulty level (easy, medium, hard, etc.)
        category: Category for organization (Health, Productivity, etc.)

    Relationships:
        user_mq: All UserMissionQuest instances referencing this template
    """

    __tablename__ = "mq_templates"

    # Primary key - UUID stored as string for SQLite compatibility
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # Quest identity
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description_template: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Quest type and structure
    # type: daily, timed, periodic, repeatable, story_arc, side_quest, etc.
    type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # structure: single_action, multi_action, multi_part
    structure: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Completion condition - JSON for flexibility
    # Examples:
    # {"type": "yes_no"} - Simple yes/no completion
    # {"type": "accumulation", "target": 50} - Accumulate 50 units
    # {"type": "quality", "threshold": 0.8} - Quality threshold
    completion_condition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Rewards
    reward_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Difficulty: easy, medium, hard, extreme, etc.
    difficulty: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)

    # Organization
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================

    user_mq: Mapped[list["UserMissionQuest"]] = relationship(
        "UserMissionQuest",
        back_populates="template",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<MissionQuestTemplate {self.name} ({self.type or 'untyped'})>"


class UserMissionQuest(Base):
    """
    User-specific mission/quest instance.

    UserMissionQuest tracks a user's progress on a specific quest. It can
    reference a MissionQuestTemplate (for reusable quests) or be standalone
    (for custom user-created quests).

    Supports hierarchical structure through self-referential parent_mq_id,
    allowing quests to have child quests (e.g., Story Arc -> Mission -> Sub-quest).

    Attributes:
        id: Unique identifier (UUID string)
        user_id: Foreign key to the user who owns this quest
        template_id: Foreign key to MissionQuestTemplate (nullable for custom quests)
        parent_mq_id: Self-referential foreign key for quest hierarchy
        name: Quest name (can be personalized)
        personalized_description: AI-generated description for this user
        status: Current status (not_started, in_progress, completed, failed)
        completion_progress: Current progress value (for accumulation quests)
        completion_target: Target value for completion (default 100 for percentage)
        created_at: When this quest instance was created
        deadline: Optional deadline for timed quests
        completed_at: When the quest was completed (if applicable)

    Relationships:
        user: The user who owns this quest
        template: The template this quest is based on (if any)
        parent_mq: The parent quest (for hierarchical quests)
        child_mq: Child quests under this quest
    """

    __tablename__ = "user_mq"

    # Primary key - UUID stored as string for SQLite compatibility
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # Foreign keys
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    template_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("mq_templates.id"),
        nullable=True,  # Nullable for custom quests not based on templates
        index=True,
    )

    # Self-referential foreign key for quest hierarchy
    parent_mq_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("user_mq.id"),
        nullable=True,
        index=True,
    )

    # Quest identity
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    personalized_description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Status tracking
    # Valid statuses: not_started, in_progress, completed, failed
    status: Mapped[str] = mapped_column(String(20), default="not_started", nullable=False)

    # Progress tracking (for accumulation-type quests)
    completion_progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_target: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    # Flexible metadata storage (for frequency tracking, etc.)
    quest_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        default=dict,
        nullable=False,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================

    user: Mapped["User"] = relationship(
        "User",
        back_populates="user_mq",
    )

    template: Mapped[Optional["MissionQuestTemplate"]] = relationship(
        "MissionQuestTemplate",
        back_populates="user_mq",
    )

    # Self-referential relationship for quest hierarchy
    parent_mq: Mapped[Optional["UserMissionQuest"]] = relationship(
        "UserMissionQuest",
        remote_side="UserMissionQuest.id",
        back_populates="child_mq",
        foreign_keys="UserMissionQuest.parent_mq_id",
    )

    child_mq: Mapped[list["UserMissionQuest"]] = relationship(
        "UserMissionQuest",
        back_populates="parent_mq",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<UserMissionQuest {self.name} ({self.status})>"

    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        if self.completion_target == 0:
            return 100.0 if self.completion_progress > 0 else 0.0
        return (self.completion_progress / self.completion_target) * 100

    def update_progress(self, amount: int) -> bool:
        """
        Update completion progress and check if quest is completed.

        Args:
            amount: Amount to add to completion_progress

        Returns:
            bool: True if quest is now completed, False otherwise
        """
        self.completion_progress += amount

        if self.completion_progress >= self.completion_target:
            self.status = "completed"
            self.completed_at = datetime.utcnow()
            return True

        if self.status == "not_started":
            self.status = "in_progress"

        return False

    def start(self) -> None:
        """Mark quest as in_progress if not already started."""
        if self.status == "not_started":
            self.status = "in_progress"

    def complete(self) -> None:
        """Mark quest as completed."""
        self.status = "completed"
        self.completed_at = datetime.utcnow()
        self.completion_progress = self.completion_target

    def fail(self) -> None:
        """Mark quest as failed."""
        self.status = "failed"
