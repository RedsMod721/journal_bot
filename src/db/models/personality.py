"""Personality state/message/memory tables."""

import uuid
from datetime import datetime, timezone

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
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class PersonalityState(Base):
    __tablename__ = "personality_states"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    active_personality: Mapped[str] = mapped_column(
        String(50), nullable=False, default="observer"
    )
    selection_factors_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    selector_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    multi_personality_annotations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_personality_states_user"),
        Index("idx_personality_states_user", "user_id"),
        CheckConstraint(
            "active_personality IN ('observer','therapist','coach','sassy','wargod','raphael')",
            name="ck_personality_states_active_personality",
        ),
        CheckConstraint(
            "multi_personality_annotations IN (0,1)",
            name="ck_personality_states_annotations",
        ),
    )


class PersonalityMessage(Base):
    __tablename__ = "personality_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entry_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=True
    )
    quest_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("quests.id", ondelete="SET NULL"), nullable=True
    )
    personality: Mapped[str] = mapped_column(String(50), nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    selector_seed_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    selector_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    logical_slot_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_personality_msgs_user", "user_id"),
        Index("idx_personality_msgs_user_sent", "user_id", "sent_at"),
        Index("idx_personality_msgs_user_entry", "user_id", "entry_id"),
        Index(
            "idx_personality_msgs_user_entry_type",
            "user_id",
            "entry_id",
            "message_type",
        ),
        Index("idx_personality_msgs_personality", "personality"),
        Index("idx_personality_msgs_selector_seed", "user_id", "selector_seed_hash"),
        UniqueConstraint(
            "user_id",
            "entry_id",
            "message_type",
            "logical_slot_key",
            "selector_version",
            name="uq_personality_messages_selector_slot",
        ),
        CheckConstraint(
            "personality IN ('observer','therapist','coach','sassy','wargod','raphael')",
            name="ck_personality_messages_personality",
        ),
    )


class PersonalityMemory(Base):
    __tablename__ = "personality_memory"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    memory_key: Mapped[str] = mapped_column(String(100), nullable=False)
    memory_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "tier", "memory_key", name="uq_personality_memory_key"
        ),
        Index("idx_personality_memory_user", "user_id"),
        Index("idx_personality_memory_user_tier", "user_id", "tier"),
        Index("idx_personality_memory_expires", "expires_at"),
        CheckConstraint(
            "tier IN ('short_term','mid_term','long_term')",
            name="ck_personality_memory_tier",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_personality_memory_confidence",
        ),
    )
