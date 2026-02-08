"""
User model for Status Window API.

The User is the central entity that owns all game-related data:
themes, skills, titles, journal entries, missions/quests, and stats.

All relationships use cascade delete to ensure data integrity
when a user is deleted.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.utils.database import Base


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
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # User identity fields
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Account metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # =========================================================================
    # RELATIONSHIPS
    # All relationships use back_populates for bidirectional access
    # cascade="all, delete-orphan" ensures related records are deleted with user
    # =========================================================================

    themes: Mapped[list["Theme"]] = relationship(
        "Theme",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    skills: Mapped[list["Skill"]] = relationship(
        "Skill",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    journal_entries: Mapped[list["JournalEntry"]] = relationship(
        "JournalEntry",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    user_titles: Mapped[list["UserTitle"]] = relationship(
        "UserTitle",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    user_mq: Mapped[list["UserMissionQuest"]] = relationship(
        "UserMissionQuest",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    stats: Mapped[Optional["UserStats"]] = relationship(
        "UserStats",
        back_populates="user",
        uselist=False,  # One-to-one relationship
        cascade="all, delete-orphan",
    )

    event_logs: Mapped[list["EventLog"]] = relationship(
        "EventLog",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    items: Mapped[list["UserItem"]] = relationship(
        "UserItem",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<User {self.username}>"
