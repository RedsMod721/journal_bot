"""Personality state/message/memory tables — v2.

Three tables drive the personality system:

personality_states
    One row per user. user_id is the PK (true 1-to-1 with users).
    Stores active personality, per-personality likability scores (0-100),
    and tunable settings (short-term memory window, message caps, etc.).

personality_messages
    Immutable log of every LLM-generated personality message.
    The uq_personality_messages_exactly_once constraint ensures a given
    (user, entry, message_type, personality) combo is written at most once,
    making pipeline retries safe.

personality_memory
    Tiered key-value store ('thread' | 'short_term' | 'long_term') that
    lets personalities recall facts across sessions.
    uq_personality_memory_idempotent ensures upsert-by-key is safe.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.journal_entry import JournalEntry
    from src.db.models.quest import Quest
    from src.db.models.user import User

_PERSONALITY_CHECK = (
    "personality IN ('observer','therapist','coach','sassy','wargod','raphael','system')"
)
_ACTIVE_PERSONALITY_CHECK = (
    "active_personality IN ('observer','therapist','coach','sassy','wargod','raphael')"
)
_MESSAGE_TYPE_CHECK = (
    "message_type IN ("
    "'entry_feedback','quest_complete','level_up','arc_trigger',"
    "'safety_intervention','entry_ack','quest_nudge','report_summary'"
    ")"
)


class PersonalityState(Base):
    """One row per user — active personality + likability + tunable settings."""

    __tablename__ = "personality_states"

    # PK is the user FK (true 1-to-1)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    active_personality: Mapped[str] = mapped_column(
        String(50), nullable=False, default="observer"
    )

    # ------------------------------------------------------------------
    # Likability scores (0-100)
    # ------------------------------------------------------------------
    likability_observer: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    likability_therapist: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    likability_coach: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    likability_sassy: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    likability_wargod: Mapped[int] = mapped_column(Integer, nullable=False, default=40)
    likability_raphael: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    # ------------------------------------------------------------------
    # Tunable settings
    # ------------------------------------------------------------------
    memory_short_term_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7
    )
    multi_personality_annotations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    switch_cooldown_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=600
    )
    max_messages_per_entry: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    max_message_chars: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_annotation_chars: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ------------------------------------------------------------------
    # Selection state
    # ------------------------------------------------------------------
    last_selection_factors: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}"
    )
    last_switched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship(
        "User",
        back_populates="personality_state",
    )

    # ------------------------------------------------------------------
    # Constraints & indexes
    # ------------------------------------------------------------------
    __table_args__ = (
        CheckConstraint(_ACTIVE_PERSONALITY_CHECK, name="ck_personality_states_active_personality"),
        CheckConstraint("multi_personality_annotations IN (0,1)", name="ck_personality_states_annotations"),
        CheckConstraint("likability_observer BETWEEN 0 AND 100", name="ck_ps_likability_observer"),
        CheckConstraint("likability_therapist BETWEEN 0 AND 100", name="ck_ps_likability_therapist"),
        CheckConstraint("likability_coach BETWEEN 0 AND 100", name="ck_ps_likability_coach"),
        CheckConstraint("likability_sassy BETWEEN 0 AND 100", name="ck_ps_likability_sassy"),
        CheckConstraint("likability_wargod BETWEEN 0 AND 100", name="ck_ps_likability_wargod"),
        CheckConstraint("likability_raphael BETWEEN 0 AND 100", name="ck_ps_likability_raphael"),
        CheckConstraint("switch_cooldown_seconds >= 0", name="ck_ps_switch_cooldown"),
        CheckConstraint("memory_short_term_days >= 1", name="ck_ps_memory_days"),
    )

    def __repr__(self) -> str:
        return f"<PersonalityState user_id={self.user_id!r} active={self.active_personality!r}>"

    def likability_for(self, personality: str) -> int:
        """Return the current likability score for the named personality."""
        return getattr(self, f"likability_{personality}", 0)


class PersonalityMessage(Base):
    """Immutable log of personality-generated messages, one per logical slot."""

    __tablename__ = "personality_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entry_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False
    )
    personality: Mapped[str] = mapped_column(String(50), nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    selector_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    selector_seed_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    logical_slot_key: Mapped[str] = mapped_column(
        String(100), nullable=False, default="default"
    )
    context_data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    quest_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("quests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship("User", back_populates="personality_messages")
    entry: Mapped["JournalEntry"] = relationship(
        "JournalEntry", back_populates="personality_messages"
    )
    quest: Mapped[Optional["Quest"]] = relationship(
        "Quest", back_populates="personality_messages"
    )

    # ------------------------------------------------------------------
    # Constraints & indexes
    # ------------------------------------------------------------------
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "entry_id",
            "message_type",
            "logical_slot_key",
            "selector_version",
            name="uq_personality_messages_selector_slot",
        ),
        CheckConstraint(_PERSONALITY_CHECK, name="ck_personality_messages_personality"),
        CheckConstraint(
            _MESSAGE_TYPE_CHECK,
            name="ck_personality_messages_message_type",
        ),
        Index("idx_personality_messages_user", "user_id"),
        Index("idx_personality_messages_entry", "entry_id"),
        Index("idx_personality_messages_user_entry", "user_id", "entry_id"),
        Index(
            "idx_personality_messages_user_entry_type",
            "user_id",
            "entry_id",
            "message_type",
        ),
        Index(
            "idx_personality_messages_selector_seed",
            "user_id",
            "selector_seed_hash",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PersonalityMessage id={self.id!r}"
            f" personality={self.personality!r}"
            f" type={self.message_type!r}>"
        )


class PersonalityMemory(Base):
    """Tiered key-value memory store for personality context."""

    __tablename__ = "personality_memory"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # 'thread' | 'short_term' | 'long_term'
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship("User", back_populates="personality_memories")

    # ------------------------------------------------------------------
    # Constraints & indexes
    # ------------------------------------------------------------------
    __table_args__ = (
        UniqueConstraint(
            "user_id", "tier", "key", name="uq_personality_memory_idempotent"
        ),
        CheckConstraint(
            "tier IN ('thread','short_term','long_term')",
            name="ck_personality_memory_tier",
        ),
        Index("idx_personality_memory_user_tier", "user_id", "tier"),
        Index("idx_personality_memory_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<PersonalityMemory id={self.id!r} tier={self.tier!r} key={self.key!r}>"
