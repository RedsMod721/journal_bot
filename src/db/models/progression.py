"""Progression history tables."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class LevelUp(Base):
    __tablename__ = "level_ups"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    old_level: Mapped[int] = mapped_column(Integer, nullable=False)
    new_level: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_level_ups_user", "user_id"),
        CheckConstraint(
            "target_type IN ('skill','theme','user')", name="ck_level_ups_target_type"
        ),
        CheckConstraint("old_level >= 0", name="ck_level_ups_old_level"),
        CheckConstraint("new_level >= old_level", name="ck_level_ups_new_level"),
    )
