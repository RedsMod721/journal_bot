"""Anomaly scoring table."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class AnomalyScore(Base):
    __tablename__ = "anomaly_scores"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reasons_json: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_anomaly_scores_user_entry",
        ),
        Index("idx_anomaly_scores_user", "user_id"),
        Index("idx_anomaly_scores_user_entry", "user_id", "entry_id"),
        CheckConstraint("score >= 0 AND score <= 1.0", name="ck_anomaly_scores_score"),
    )
