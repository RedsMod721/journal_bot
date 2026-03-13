"""Anomaly scoring table (schema v2).

score     — float, 0.0–10.0  (Section 9.0.1)
troll_multiplier — float, 1.0–5.0  (Section 9.6 / A.6.1)
detection_factors — JSON text, privacy-safe signal labels only (Section 9.0.5)
calculated_at — UTC datetime of computation
"""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class AnomalyScore(Base):
    __tablename__ = "anomaly_scores"

    # Composite PK — one row per (user, entry), idempotent by design
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True, nullable=False)

    # Score on 0–10 scale (architecture canonical)
    score: Mapped[float] = mapped_column(Float, nullable=False)

    # Pre-computed XP/coin multiplier derived from score
    troll_multiplier: Mapped[float] = mapped_column(Float, nullable=False)

    # JSON array of privacy-safe signal labels (NEVER raw user text)
    detection_factors: Mapped[str] = mapped_column(Text, nullable=False)

    calculated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_anomaly_scores_entry",
        ),
        Index("idx_anomaly_scores_user", "user_id"),
        Index("idx_anomaly_scores_score", "score"),
        CheckConstraint(
            "score >= 0.0 AND score <= 10.0",
            name="ck_anomaly_score_range",
        ),
        CheckConstraint(
            "troll_multiplier >= 1.0 AND troll_multiplier <= 5.0",
            name="ck_troll_multiplier_range",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AnomalyScore(entry_id={self.entry_id!r}, "
            f"score={self.score}, multiplier={self.troll_multiplier})>"
        )
