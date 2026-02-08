"""
User model for Status Window API.

The User is the central entity that owns all game-related data:
themes, skills, titles, journal entries, missions/quests, and stats.

All relationships use cascade delete to ensure data integrity
when a user is deleted.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.orm import relationship

from app.utils.database import Base

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapped


class User(Base):
    """
    User model representing a player in the Status Window system.

    Attributes:
        id: Unique identifier (UUID string)
        username: Unique username for display and login
        email: Unique email address
        created_at: Timestamp of account creation
        is_active: Whether the user account is active

    Relationships:
        themes: User's life themes (one-to-many)
        skills: User's skills (one-to-many)
        journal_entries: User's journal entries (one-to-many)
        user_titles: User's earned titles (one-to-many)
        user_mq: User's missions and quests (one-to-many)
        stats: User's status bars - HP, MP, etc. (one-to-one)
    """

    __tablename__ = "users"

    # Primary key - UUID stored as string for SQLite compatibility
    id: str = Column(  # type: ignore
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # User identity fields
    username: str = Column(String(50), unique=True, nullable=False, index=True)  # type: ignore
    email: str = Column(String(255), unique=True, nullable=False, index=True)  # type: ignore

    # Account metadata
    created_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)  # type: ignore
    is_active: bool = Column(Boolean, default=True, nullable=False)  # type: ignore

    # =========================================================================
    # RELATIONSHIPS
    # All relationships use back_populates for bidirectional access
    # cascade="all, delete-orphan" ensures related records are deleted with user
    # =========================================================================

    themes = relationship(
        "Theme",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    skills = relationship(
        "Skill",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    journal_entries = relationship(
        "JournalEntry",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    user_titles = relationship(
        "UserTitle",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    user_mq = relationship(
        "UserMissionQuest",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    stats = relationship(
        "UserStats",
        back_populates="user",
        uselist=False,  # One-to-one relationship
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<User {self.username}>"
