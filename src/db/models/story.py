"""Story arc tables."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class StoryArc(Base):
    __tablename__ = "story_arcs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    arc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    xp_reward_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )
    quest_requirement_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )
    decay_rate_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )

    __table_args__ = (
        Index("idx_story_arcs_user", "user_id"),
        Index("idx_story_arcs_user_status", "user_id", "status"),
        UniqueConstraint("user_id", "id", name="uq_story_arcs_user_id"),
        CheckConstraint(
            "status IN ('active','completed','abandoned','paused')",
            name="ck_story_arcs_status",
        ),
        CheckConstraint(
            "decay_rate_multiplier >= 0 AND decay_rate_multiplier <= 1.0",
            name="ck_story_arcs_decay_rate_multiplier",
        ),
    )


class ArcTrigger(Base):
    __tablename__ = "arc_triggers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    arc_id: Mapped[str] = mapped_column(String(36), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_data: Mapped[str | None] = mapped_column(String, nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "arc_id"],
            ["story_arcs.user_id", "story_arcs.id"],
            ondelete="CASCADE",
            name="fk_arc_triggers_user_arc",
        ),
        Index("idx_arc_triggers_user", "user_id"),
        Index("idx_arc_triggers_user_triggered", "user_id", "triggered_at"),
    )
