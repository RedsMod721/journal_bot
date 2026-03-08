"""Strategy tracking table."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class StrategyTracking(Base):
    __tablename__ = "strategy_tracking"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    strategy_streaks_json: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_strategy_tracking_user", "user_id"),
        CheckConstraint("usage_count >= 0", name="ck_strategy_tracking_usage_count"),
        CheckConstraint(
            "success_rate >= 0 AND success_rate <= 1.0",
            name="ck_strategy_tracking_success_rate",
        ),
    )
