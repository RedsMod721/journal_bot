"""
SQLAlchemy models for journal entry tables.

Tables:
    journal_entries            — raw text / audio entries
    journal_entries_structured — AI-extracted structured fields (Q7)
    entry_attachments          — file attachments (images, PDFs)
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
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.user import User


class JournalEntry(Base):
    """
    Raw journal entry submitted by the user.

    Content may be plain text or a transcription of an audio recording.
    Processing progresses through `status` states; Q6 multi-round question
    state is tracked via `question_state`.

    Multi-tenant isolation:
        UNIQUE(user_id, id) allows composite FK references from child tables
        (e.g. journal_entries_structured) for tenant-safe cascade behaviour.
    """

    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------
    content: Mapped[str] = mapped_column(Text, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # ------------------------------------------------------------------
    # Processing state
    # ------------------------------------------------------------------
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")

    # ------------------------------------------------------------------
    # Q6: Multi-round questions
    # ------------------------------------------------------------------
    # Tracks whether the AI pipeline is waiting for a user follow-up answer
    question_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none"
    )
    questions_asked: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON array
    question_timeout: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    recorded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True  # Populated for audio entries
    )
    transcription_confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # ------------------------------------------------------------------
    # Processing results
    # ------------------------------------------------------------------
    processing_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship("User", back_populates="journal_entries")
    structured: Mapped[Optional["JournalEntryStructured"]] = relationship(
        "JournalEntryStructured",
        back_populates="entry",
        cascade="all, delete-orphan",
        uselist=False,
    )
    attachments: Mapped[list["EntryAttachment"]] = relationship(
        "EntryAttachment",
        back_populates="entry",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_journal_entries_user_id"),
        Index("idx_entries_user", "user_id"),
        Index("idx_entries_user_created", "user_id", "created_at"),
        Index("idx_entries_user_status", "user_id", "status"),
        Index("idx_entries_created", "created_at"),
        CheckConstraint(
            "entry_type IN ('text','audio','split','other')",
            name="ck_journal_entries_entry_type",
        ),
        CheckConstraint(
            "status IN ('pending','processing','completed','failed','pending_other_type')",
            name="ck_journal_entries_status",
        ),
        CheckConstraint(
            "question_state IN ('none','pending','answered','timeout')",
            name="ck_journal_entries_question_state",
        ),
        CheckConstraint(
            "transcription_confidence IS NULL OR "
            "(transcription_confidence >= 0 AND transcription_confidence <= 1.0)",
            name="ck_journal_entries_transcription_confidence",
        ),
    )

    def __repr__(self) -> str:
        return f"<JournalEntry id={self.id!r} user_id={self.user_id!r} status={self.status!r}>"


class JournalEntryStructured(Base):
    """
    AI-extracted structured fields for a journal entry (Q7 — 13 new fields).

    One row per entry (1-to-1). Created by the processing pipeline after the
    raw entry is parsed. Composite FK (user_id, entry_id) enforces that the
    structured row belongs to the same tenant as its parent entry.
    """

    __tablename__ = "journal_entries_structured"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # ------------------------------------------------------------------
    # Q7: Structured extraction fields
    # ------------------------------------------------------------------
    canonical_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    primary_action_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True  # e.g. run, code, study, cook
    )
    goal_relation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    time_of_day_bucket: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    dominant_emotions: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON array
    energy_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1–10
    self_compassion_score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # 0–10

    task_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True  # creative, analytical, physical, social
    )
    success_quality: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # 0–10
    blockers_or_obstacles: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    support_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delay_from_planned_time_minutes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    reflection_depth: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    skills_themes_involved: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON array

    # ------------------------------------------------------------------
    # Original categorisation fields
    # ------------------------------------------------------------------
    categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    sentiment_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # -1.0–1.0

    # Safety / crisis flags
    safety_flags: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON array

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    entry: Mapped["JournalEntry"] = relationship(
        "JournalEntry",
        back_populates="structured",
        foreign_keys=[entry_id],
        primaryjoin="JournalEntryStructured.entry_id == JournalEntry.id",
    )

    __table_args__ = (
        # Composite FK — tenant-safe cascade from journal_entries
        ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_journal_entries_structured_user_entry",
        ),
        UniqueConstraint(
            "user_id", "entry_id", name="uq_journal_entries_structured_user_entry"
        ),
        UniqueConstraint("user_id", "id", name="uq_journal_entries_structured_user_id"),
        Index("idx_entries_struct_user", "user_id"),
        Index("idx_entries_struct_user_entry", "user_id", "entry_id"),
        CheckConstraint(
            "time_of_day_bucket IS NULL OR "
            "time_of_day_bucket IN ('morning','afternoon','evening','night')",
            name="ck_structured_time_of_day_bucket",
        ),
        CheckConstraint(
            "energy_level IS NULL OR (energy_level >= 1 AND energy_level <= 10)",
            name="ck_structured_energy_level",
        ),
        CheckConstraint(
            "self_compassion_score IS NULL OR "
            "(self_compassion_score >= 0 AND self_compassion_score <= 10)",
            name="ck_structured_self_compassion_score",
        ),
        CheckConstraint(
            "success_quality IS NULL OR (success_quality >= 0 AND success_quality <= 10)",
            name="ck_structured_success_quality",
        ),
        CheckConstraint(
            "reflection_depth IS NULL OR "
            "reflection_depth IN ('surface','moderate','deep')",
            name="ck_structured_reflection_depth",
        ),
        CheckConstraint(
            "sentiment_score IS NULL OR (sentiment_score >= -1 AND sentiment_score <= 1)",
            name="ck_structured_sentiment_score",
        ),
    )

    def __repr__(self) -> str:
        return f"<JournalEntryStructured entry_id={self.entry_id!r}>"


class EntryAttachment(Base):
    """
    File attachment linked to a journal entry.

    Stores metadata only — the file itself lives on disk (or object storage).
    `ocr_text` is populated after image processing by the pipeline.
    """

    __tablename__ = "entry_attachments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # File metadata
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)  # MIME type
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Processing
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    entry: Mapped["JournalEntry"] = relationship(
        "JournalEntry",
        back_populates="attachments",
        foreign_keys=[entry_id],
        primaryjoin="EntryAttachment.entry_id == JournalEntry.id",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_entry_attachments_user_entry",
        ),
        Index("idx_attachments_user_entry", "user_id", "entry_id"),
        CheckConstraint(
            "file_size_bytes > 0",
            name="ck_entry_attachments_file_size_bytes",
        ),
    )

    def __repr__(self) -> str:
        return f"<EntryAttachment id={self.id!r} entry_id={self.entry_id!r}>"
