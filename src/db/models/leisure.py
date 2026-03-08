"""Leisure system tables (Q31)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class LeisureBudget(Base):
    __tablename__ = "leisure_budget"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    period_key: Mapped[str] = mapped_column(String(20), nullable=False)
    coins_budgeted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coins_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("user_id", "period_key", name="uq_leisure_budget_user_period"),
        Index("idx_leisure_budget_user", "user_id"),
        CheckConstraint("coins_budgeted >= 0", name="ck_leisure_budget_budgeted"),
        CheckConstraint("coins_spent >= 0", name="ck_leisure_budget_spent"),
    )


class SubstanceLimit(Base):
    __tablename__ = "substance_limits"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    substance_name: Mapped[str] = mapped_column(String(100), nullable=False)
    max_units_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "substance_name", name="uq_substance_limits_user_substance"
        ),
        Index("idx_substance_limits_user", "user_id"),
        CheckConstraint("max_units_per_day >= 0", name="ck_substance_limits_max_units"),
        CheckConstraint("enabled IN (0,1)", name="ck_substance_limits_enabled"),
    )


class SubstanceUsageLog(Base):
    __tablename__ = "substance_usage_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    substance_name: Mapped[str] = mapped_column(String(100), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False)
    used_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("idx_substance_usage_log_user", "user_id"),
        Index("idx_substance_usage_log_user_used", "user_id", "used_at"),
        CheckConstraint("units > 0", name="ck_substance_usage_log_units"),
    )
