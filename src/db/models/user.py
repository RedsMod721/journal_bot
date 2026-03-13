"""
SQLAlchemy model for the users table.

The User is the central tenant entity. All game data (skills, themes, quests,
journal entries) is owned by a User and cascade-deleted with it.

Circular FK note:
    users.forgiveness_config_id → forgiveness_configs.id
    forgiveness_configs.user_id → users.id

    This is resolved with `use_alter=True` so SQLAlchemy emits the FK as a
    deferred ALTER TABLE after both tables are created.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.realm import default_user_preferences
from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.forgiveness import DecaySnapshot, ForgivenessConfig
    from src.db.models.journal_entry import JournalEntry
    from src.db.models.personality import PersonalityMemory, PersonalityMessage, PersonalityState
    from src.db.models.quest import Quest, QuestFailureTracker
    from src.db.models.skill import Skill, Theme
    from src.db.models.user_skill_state import UserSkillState
    from src.db.models.xp import XpAward  # noqa: F401


class User(Base):
    """
    Core user account for the RPG Life Tracker.

    Stores authentication credentials, profile preferences, localization
    settings, and Q27 learning-system state. Acts as the root of all
    cascade deletes: removing a user removes all their game data.

    Personality / forgiveness:
        - `forgiveness_config_id` points to the row that controls skill decay.
          This FK is deferred (`use_alter=True`) because forgiveness_configs
          also references users.
        - `current_personality` is a cache of the active personality state
          (authoritative row lives in personality_states, added in a later
          migration).

    Localization / safety:
        - `home_country` (ISO 3166-1 alpha-2) drives crisis-resource routing.
        - IP geolocation is opt-in; `last_known_country` is only stored when
          `allow_ip_geolocation` is True.

    Q27 learning-system fields:
        - `learning_phase_complete`: True after 10 quests per skill.
        - `quest_decisions_count`: Total accumulated quest decisions.
        - `confidence_threshold_instant/longterm`: User-adjustable thresholds.
    """

    __tablename__ = "users"

    # ------------------------------------------------------------------
    # Primary key
    # ------------------------------------------------------------------
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------
    username: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, nullable=True
    )
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Localization
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")

    # Crisis/localization — ISO 3166-1 alpha-2, application validates uppercase
    home_country: Mapped[str] = mapped_column(String(2), nullable=False, default="FR")
    allow_ip_geolocation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    last_known_country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    country_last_resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # ------------------------------------------------------------------
    # Forgiveness / decay (FK is deferred — see use_alter below)
    # ------------------------------------------------------------------
    forgiveness_config_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey(
            "forgiveness_configs.id",
            use_alter=True,
            name="fk_users_forgiveness_config_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # ------------------------------------------------------------------
    # Q27: Learning system
    # ------------------------------------------------------------------
    learning_phase_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    quest_decisions_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # User-adjustable thresholds for instant vs. long-term quest classification
    confidence_threshold_instant: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.65
    )
    confidence_threshold_longterm: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.45
    )

    # ------------------------------------------------------------------
    # System / personality
    # ------------------------------------------------------------------
    active_arc_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("story_arcs.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Cache of current personality state (authoritative: personality_states table)
    current_personality: Mapped[str] = mapped_column(
        String(50), nullable=False, default="observer"
    )
    allow_trusted_nodes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # ------------------------------------------------------------------
    # Skill hierarchy preferences
    # ------------------------------------------------------------------
    # When True, newly discovered sub-skills default to user_blocked=True
    # in user_skill_states (user must manually unblock them).
    default_blocked_preference: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Future-facing personalization container. For now:
    # user_preferences.realm.scope + user_preferences.realm.ranks_wording.preset
    user_preferences: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=default_user_preferences
    )

    # ------------------------------------------------------------------
    # Moderation / admin
    # ------------------------------------------------------------------
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    banned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ban_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    # Navigate User → ForgivenessConfig via users.forgiveness_config_id.
    # Not paired with back_populates: the circular FK pair means both sides are
    # many-to-one and SQLAlchemy can't resolve direction automatically.
    forgiveness_config: Mapped[Optional["ForgivenessConfig"]] = relationship(
        "ForgivenessConfig",
        foreign_keys=[forgiveness_config_id],
        uselist=False,
        overlaps="user",
    )
    skills: Mapped[list["Skill"]] = relationship(
        "Skill",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    themes: Mapped[list["Theme"]] = relationship(
        "Theme",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    journal_entries: Mapped[list["JournalEntry"]] = relationship(
        "JournalEntry",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    quests: Mapped[list["Quest"]] = relationship(
        "Quest",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    xp_awards: Mapped[list["XpAward"]] = relationship(
        "XpAward",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    quest_failure_trackers: Mapped[list["QuestFailureTracker"]] = relationship(
        "QuestFailureTracker",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    decay_snapshots: Mapped[list["DecaySnapshot"]] = relationship(
        "DecaySnapshot",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    skill_states: Mapped[list["UserSkillState"]] = relationship(
        "UserSkillState",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    personality_state: Mapped[Optional["PersonalityState"]] = relationship(
        "PersonalityState",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    personality_messages: Mapped[list["PersonalityMessage"]] = relationship(
        "PersonalityMessage",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    personality_memories: Mapped[list["PersonalityMemory"]] = relationship(
        "PersonalityMemory",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------------------
    # Indexes & constraints
    # ------------------------------------------------------------------
    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_username", "username"),
        Index("idx_users_created", "created_at"),
        CheckConstraint(
            "quest_decisions_count >= 0",
            name="ck_users_quest_decisions_count",
        ),
        CheckConstraint(
            "confidence_threshold_instant >= 0 AND confidence_threshold_instant <= 1.0",
            name="ck_users_confidence_instant",
        ),
        CheckConstraint(
            "confidence_threshold_longterm >= 0 AND confidence_threshold_longterm <= 1.0",
            name="ck_users_confidence_longterm",
        ),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r} username={self.username!r}>"
