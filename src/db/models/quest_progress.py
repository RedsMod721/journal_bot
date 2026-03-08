"""Quest progress persistence for long-term quest tracking."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class QuestProgress(Base):
    __tablename__ = "quest_progress"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    quest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    progress_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streak_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streak_best: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_progress_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "quest_id"],
            ["quests.user_id", "quests.id"],
            ondelete="CASCADE",
            name="fk_quest_progress_user_quest",
        ),
        UniqueConstraint("user_id", "quest_id", name="uq_quest_progress_user_quest"),
        Index("idx_quest_progress_user", "user_id"),
        CheckConstraint("progress_value >= 0", name="ck_quest_progress_value"),
        CheckConstraint("streak_current >= 0", name="ck_quest_progress_streak_current"),
        CheckConstraint("streak_best >= 0", name="ck_quest_progress_streak_best"),
    )
