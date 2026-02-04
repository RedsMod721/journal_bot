"""
Title models for Status Window API.

This module contains two related models:
1. TitleTemplate - Global title bank (shared across all users)
2. UserTitle - User-specific title instances

Titles are achievements/badges that recognize accomplishments and provide
passive buffs/debuffs (stored in the effect JSON field). All player weights
are contained in titles, making them the core modifier system.

Features:
- Rank system (F, E, D, C, B, A, S)
- Hidden titles (unlock conditions teased but not revealed)
- Temporary titles with expiration
- JSON-stored effects and unlock conditions for flexibility
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import relationship

from app.utils.database import Base


class TitleTemplate(Base):
    """
    Global title bank containing all available title definitions.

    TitleTemplates are shared across all users and define the title's
    properties, effects, and unlock conditions. When a user earns a title,
    a UserTitle instance is created referencing this template.

    Attributes:
        id: Unique identifier (UUID string)
        name: Title name (e.g., "Early Riser", "Social Butterfly")
        description_template: Template with {user_name} placeholders
        effect: JSON containing buff/debuff effects
        rank: Title rank (F, E, D, C, B, A, S)
        unlock_condition: JSON defining how to unlock this title
        category: Category for organization (Social, Productivity, etc.)
        is_hidden: Whether unlock conditions are hidden until earned

    Relationships:
        user_titles: All UserTitle instances referencing this template
    """

    __tablename__ = "title_templates"

    # Primary key - UUID stored as string for SQLite compatibility
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # Title identity
    name = Column(String(100), unique=True, nullable=False, index=True)
    description_template = Column(String(500), nullable=True)

    # Effect system - JSON for flexibility
    # Example: {"type": "xp_multiplier", "scope": "theme", "target": "Education", "value": 1.10}
    effect = Column(JSON, default=dict, nullable=False)

    # Rank system (F to S, like Korean RPG novels)
    rank = Column(String(1), default="D", nullable=False)

    # Unlock condition - JSON for flexibility
    # Example: {"type": "journal_streak", "value": 7}
    unlock_condition = Column(JSON, default=dict, nullable=False)

    # Organization
    category = Column(String(50), nullable=True, index=True)

    # Hidden titles - conditions teased but not fully revealed
    is_hidden = Column(Boolean, default=False, nullable=False)

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================

    user_titles = relationship(
        "UserTitle",
        back_populates="title_template",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<TitleTemplate {self.name} (Rank {self.rank})>"


class UserTitle(Base):
    """
    User-specific title instance linking a user to a title template.

    When a user earns a title, a UserTitle record is created. This allows
    tracking acquisition date, equipped status, personalized descriptions,
    and expiration for temporary titles.

    Attributes:
        id: Unique identifier (UUID string)
        user_id: Foreign key to the user who earned this title
        title_template_id: Foreign key to the title template
        acquired_at: When the user earned this title
        is_equipped: Whether the title's effects are active
        personalized_description: AI-generated description for this user
        expires_at: When the title expires (None for permanent titles)

    Relationships:
        user: The user who owns this title
        title_template: The template defining this title
    """

    __tablename__ = "user_titles"

    # Primary key - UUID stored as string for SQLite compatibility
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # Foreign keys
    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    title_template_id = Column(
        String(36),
        ForeignKey("title_templates.id"),
        nullable=False,
        index=True,
    )

    # Acquisition metadata
    acquired_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Equipped status - titles can be equipped/unequipped for passive effects
    is_equipped = Column(Boolean, default=True, nullable=False)

    # Personalized description - AI-generated for this specific user
    personalized_description = Column(String(500), nullable=True)

    # Expiration for temporary titles (None = permanent)
    expires_at = Column(DateTime, nullable=True)

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================

    user = relationship(
        "User",
        back_populates="user_titles",
    )

    title_template = relationship(
        "TitleTemplate",
        back_populates="user_titles",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        template_name = (
            self.title_template.name if self.title_template else "Unknown"
        )
        equipped_status = "Equipped" if self.is_equipped else "Unequipped"
        return f"<UserTitle {template_name} ({equipped_status})>"
