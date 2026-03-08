"""Harmony system tables."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class HarmonyDimension(Base):
    __tablename__ = "harmony_dimensions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "dimension", name="uq_harmony_dimensions_user_dimension"
        ),
        Index("idx_harmony_dimensions_user", "user_id"),
        CheckConstraint(
            "score >= 0 AND score <= 1.0", name="ck_harmony_dimensions_score"
        ),
    )


class HarmonySnapshot(Base):
    __tablename__ = "harmony_snapshots"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False)
    dimensions_json: Mapped[str] = mapped_column(String, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "snapshot_date", name="uq_harmony_snapshots_user_date"
        ),
        Index("idx_harmony_snapshots_user", "user_id"),
        Index("idx_harmony_snapshots_user_date", "user_id", "snapshot_date"),
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 1.0",
            name="ck_harmony_snapshots_overall",
        ),
    )
