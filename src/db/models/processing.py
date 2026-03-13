"""Entry pipeline idempotency/outbox/job tracking tables."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class EntryIdempotencyClaim(Base):
    __tablename__ = "entry_idempotency_claims"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    processing_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    processing_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    result_pointer_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved")
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="SET NULL",
            name="fk_entry_claims_user_entry",
        ),
        ForeignKeyConstraint(
            ["processing_job_id"],
            ["processing_jobs.id"],
            ondelete="SET NULL",
            name="fk_entry_claims_processing_job",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_entry_claims_user_key"),
        Index("idx_entry_claims_user", "user_id"),
        Index("idx_entry_claims_status", "status", "updated_at"),
        Index("idx_entry_claims_job", "processing_job_id"),
        Index("idx_entry_claims_entry", "user_id", "entry_id"),
        CheckConstraint(
            "status IN ('reserved','in_progress','completed','failed_retryable','failed_terminal')",
            name="ck_entry_claims_status",
        ),
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    entry_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    processing_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    processing_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_owner_token: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_outbox_events_user_entry",
        ),
        ForeignKeyConstraint(
            ["processing_job_id"],
            ["processing_jobs.id"],
            ondelete="SET NULL",
            name="fk_outbox_events_processing_job",
        ),
        UniqueConstraint("event_dedupe_key", name="uq_outbox_events_dedupe"),
        Index("idx_outbox_events_status_next_attempt", "status", "next_attempt_at", "created_at"),
        Index("idx_outbox_events_lease", "status", "lease_expires_at"),
        Index("idx_outbox_events_source_run", "processing_run_id"),
        Index("idx_outbox_events_user_entry", "user_id", "entry_id"),
        CheckConstraint(
            "status IN ('pending','dispatching','succeeded','failed_retryable','failed_terminal')",
            name="ck_outbox_events_status",
        ),
        CheckConstraint("retry_count >= 0", name="ck_outbox_events_retry_count"),
    )


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_name: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    final_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ruleset_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    config_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_version_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        Index("idx_processing_jobs_job", "user_id", "entry_id", "step_name"),
        Index("idx_processing_jobs_run", "user_id", "processing_run_id"),
        Index("idx_processing_jobs_status_updated", "status", "updated_at"),
        Index(
            "idx_processing_jobs_entry_pipeline",
            "user_id",
            "entry_id",
            "step_name",
            "status",
            sqlite_where=text("step_name = 'entry_pipeline'"),
        ),
        Index(
            "uq_processing_jobs_one_success",
            "user_id",
            "entry_id",
            "step_name",
            unique=True,
            sqlite_where=text("status = 'succeeded'"),
        ),
        CheckConstraint(
            "status IN ('in_progress','succeeded','failed')",
            name="ck_processing_jobs_status",
        ),
        CheckConstraint(
            "step_name IN ("
            "'categorization',"
            "'quest_generation',"
            "'insight_extraction',"
            "'voice_transcription',"
            "'report_generation',"
            "'personality_message_generation',"
            "'entry_pipeline'"
            ")",
            name="ck_processing_jobs_step_name",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_processing_jobs_attempt_count"),
    )


class ProcessingJobAttempt(Base):
    __tablename__ = "processing_job_attempts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    processing_job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    attempt_id: Mapped[int] = mapped_column(Integer, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    executor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    node_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["processing_job_id"],
            ["processing_jobs.id"],
            ondelete="CASCADE",
            name="fk_processing_job_attempts_job",
        ),
        UniqueConstraint(
            "processing_job_id",
            "attempt_id",
            name="uq_processing_job_attempts_job_attempt",
        ),
        Index("idx_processing_job_attempts_job", "processing_job_id"),
        Index("idx_processing_job_attempts_time", "attempted_at"),
        CheckConstraint(
            "attempt_id >= 1", name="ck_processing_job_attempts_attempt_id"
        ),
        CheckConstraint(
            "executor_type IN ('server_local','trusted_node')",
            name="ck_processing_job_attempts_executor_type",
        ),
        CheckConstraint(
            "status IN ('succeeded','failed','rejected','timeout')",
            name="ck_processing_job_attempts_status",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_processing_job_attempts_duration_ms",
        ),
    )
