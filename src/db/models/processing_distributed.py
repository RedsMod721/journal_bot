"""Distributed claim leasing for processing jobs."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class ProcessingJobClaim(Base):
    __tablename__ = "processing_job_claims"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_name: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False)
    lease_token: Mapped[str] = mapped_column(String(64), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
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
            name="fk_processing_job_claims_user_entry",
        ),
        UniqueConstraint(
            "user_id",
            "entry_id",
            "step_name",
            name="uq_processing_job_claims_logical",
        ),
        Index("idx_processing_job_claims_lease_expiry", "lease_expires_at"),
        Index("idx_processing_job_claims_owner", "owner_kind", "owner_id"),
        UniqueConstraint("lease_token", name="uq_processing_job_claims_lease_token"),
        CheckConstraint(
            "owner_kind IN ('server_worker','scheduler','admin_recovery')",
            name="ck_processing_job_claims_owner_kind",
        ),
    )
