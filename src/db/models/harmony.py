"""Harmony system tables (pivot schema).

Architecture §6: one row per user with 7 dimension columns + overwork tracking.
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base

_DIMS = ("physical", "mental", "social", "productivity", "rest", "growth", "creative")


class HarmonyDimension(Base):
    """One row per user — 7 dimension scores + overwork tracking.

    Dimension scores are proportions in [0.0, 1.0] reflecting the share of
    entries in a 30-day window that address each dimension.
    """

    __tablename__ = "harmony_dimensions"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # 7 dimension scores [0.0, 1.0]
    physical: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    mental: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    social: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    productivity: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    rest: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    growth: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    creative: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    # Overall balance: mean of all 7 dimensions
    overall_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    # Overwork detection (§6.4)
    overwork_stage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overwork_consecutive_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    overwork_last_evaluated_local_date: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    overwork_last_changed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint(
            "overwork_stage >= 0 AND overwork_stage <= 3",
            name="ck_harmony_dimensions_overwork_stage",
        ),
        Index("idx_harmony_dimensions_user", "user_id"),
    )

    def dim_scores(self) -> dict[str, float]:
        """Return all 7 dimension scores as a dict."""
        return {d: getattr(self, d) for d in _DIMS}

    def min_score(self) -> float:
        return min(self.dim_scores().values())

    def __repr__(self) -> str:
        return (
            f"<HarmonyDimension(user_id={self.user_id!r},"
            f" overall={self.overall_balance:.2f},"
            f" overwork_stage={self.overwork_stage})>"
        )


class HarmonySnapshot(Base):
    """Daily snapshot of harmony scores — one row per (user, date)."""

    __tablename__ = "harmony_snapshots"

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
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Dimension scores at snapshot time
    physical: Mapped[float] = mapped_column(Float, nullable=False)
    mental: Mapped[float] = mapped_column(Float, nullable=False)
    social: Mapped[float] = mapped_column(Float, nullable=False)
    productivity: Mapped[float] = mapped_column(Float, nullable=False)
    rest: Mapped[float] = mapped_column(Float, nullable=False)
    growth: Mapped[float] = mapped_column(Float, nullable=False)
    creative: Mapped[float] = mapped_column(Float, nullable=False)

    overall_balance: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "snapshot_date", name="uq_harmony_snapshots_user_date"
        ),
        Index("idx_harmony_snapshots_user", "user_id"),
        Index("idx_harmony_snapshots_user_date", "user_id", "snapshot_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<HarmonySnapshot(user_id={self.user_id!r},"
            f" date={self.snapshot_date},"
            f" overall={self.overall_balance:.2f})>"
        )
