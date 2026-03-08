"""User analytics aggregate table."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class UserAnalytics(Base):
    __tablename__ = "user_analytics"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    day_key: Mapped[str] = mapped_column(String(10), nullable=False)
    entries_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    xp_awarded_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_skills_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("user_id", "day_key", name="uq_user_analytics_user_day"),
        Index("idx_user_analytics_user", "user_id"),
    )
