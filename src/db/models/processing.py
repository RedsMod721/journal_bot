"""Entry pipeline idempotency/outbox/job tracking tables."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class EntryIdempotencyClaim(Base):
    __tablename__ = "entry_idempotency_claims"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    entry_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    processing_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="claimed")
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="SET NULL",
            name="fk_entry_claims_user_entry",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_entry_claims_user_key"),
        Index("idx_entry_claims_user", "user_id"),
        CheckConstraint(
            "status IN ('claimed','completed','failed')", name="ck_entry_claims_status"
        ),
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("event_dedupe_key", name="uq_outbox_events_dedupe"),
        Index("idx_outbox_events_status", "status"),
        CheckConstraint(
            "status IN ('pending','dispatched','failed')",
            name="ck_outbox_events_status",
        ),
        CheckConstraint("retry_count >= 0", name="ck_outbox_events_retry_count"),
    )


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_name: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_processing_jobs_user_entry",
        ),
        UniqueConstraint(
            "user_id",
            "entry_id",
            "step_name",
            "processing_run_id",
            name="uq_processing_jobs_logical",
        ),
        Index("idx_processing_jobs_user", "user_id"),
        Index("idx_processing_jobs_user_status", "user_id", "status"),
        CheckConstraint(
            "status IN ('pending','processing','completed','failed')",
            name="ck_processing_jobs_status",
        ),
    )


class ProcessingJobAttempt(Base):
    __tablename__ = "processing_job_attempts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    processing_job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["processing_job_id"],
            ["processing_jobs.id"],
            ondelete="CASCADE",
            name="fk_processing_job_attempts_job",
        ),
        UniqueConstraint(
            "processing_job_id",
            "attempt_number",
            name="uq_processing_job_attempts_job_attempt",
        ),
        Index("idx_processing_job_attempts_job", "processing_job_id"),
        CheckConstraint(
            "attempt_number > 0", name="ck_processing_job_attempts_attempt_number"
        ),
        CheckConstraint(
            "status IN ('started','completed','failed')",
            name="ck_processing_job_attempts_status",
        ),
    )
