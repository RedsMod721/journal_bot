"""Distributed claim leasing for processing jobs."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    step_name: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(100), nullable=False)
    lease_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "entry_id", "step_name", "processing_run_id"],
            [
                "processing_jobs.user_id",
                "processing_jobs.entry_id",
                "processing_jobs.step_name",
                "processing_jobs.processing_run_id",
            ],
            ondelete="CASCADE",
            name="fk_processing_job_claims_logical",
        ),
        UniqueConstraint(
            "user_id",
            "entry_id",
            "step_name",
            "processing_run_id",
            name="uq_processing_job_claims_logical",
        ),
        Index("idx_processing_job_claims_lease_until", "lease_until"),
        CheckConstraint(
            "status IN ('active','released','expired')",
            name="ck_processing_job_claims_status",
        ),
    )
