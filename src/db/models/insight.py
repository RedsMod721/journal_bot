"""Pattern/insight/evidence tables."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
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
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class Pattern(Base):
    __tablename__ = "patterns"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    pattern_type: Mapped[str] = mapped_column(String(50), nullable=False)
    pattern_key: Mapped[str] = mapped_column(String(200), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_patterns_user", "user_id"),
        Index("idx_patterns_user_type", "user_id", "pattern_type"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1.0", name="ck_patterns_confidence"
        ),
        CheckConstraint("evidence_count >= 0", name="ck_patterns_evidence_count"),
    )


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    pattern_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("patterns.id", ondelete="SET NULL"), nullable=True
    )
    insight_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_insights_user_id"),
        Index("idx_insights_user", "user_id"),
        Index("idx_insights_user_status", "user_id", "status"),
        CheckConstraint(
            "strength >= 0 AND strength <= 1.0", name="ck_insights_strength"
        ),
        CheckConstraint(
            "status IN ('active','dismissed','archived')", name="ck_insights_status"
        ),
    )


class InsightEvidence(Base):
    __tablename__ = "insight_evidence"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    insight_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    evidence_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "insight_id"],
            ["insights.user_id", "insights.id"],
            ondelete="CASCADE",
            name="fk_insight_evidence_user_insight",
        ),
        ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_insight_evidence_user_entry",
        ),
        Index("idx_insight_evidence_user", "user_id"),
        Index("idx_insight_evidence_user_insight", "user_id", "insight_id"),
        CheckConstraint("evidence_weight >= 0", name="ck_insight_evidence_weight"),
    )
