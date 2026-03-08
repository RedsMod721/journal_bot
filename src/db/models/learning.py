"""Learning-system tables (Q27)."""

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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class UserQuestPreference(Base):
    __tablename__ = "user_quest_preferences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    quest_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("quests.id", ondelete="SET NULL"), nullable=True
    )
    theme_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("themes.id", ondelete="SET NULL"), nullable=True
    )

    user_decision: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "skill_id"],
            ["skills.user_id", "skills.id"],
            ondelete="CASCADE",
            name="fk_uqp_user_skill",
        ),
        Index("idx_user_quest_preferences_user", "user_id"),
        Index("idx_user_quest_preferences_skill", "user_id", "skill_id"),
        CheckConstraint(
            "user_decision IN ('accept','decline','defer')", name="ck_uqp_decision"
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1.0)",
            name="ck_uqp_confidence",
        ),
    )


class UserQuestBias(Base):
    __tablename__ = "user_quest_biases"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    bias_type: Mapped[str] = mapped_column(String(50), nullable=False)
    bias_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    observations_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "skill_id"],
            ["skills.user_id", "skills.id"],
            ondelete="CASCADE",
            name="fk_uqb_user_skill",
        ),
        UniqueConstraint(
            "user_id", "skill_id", "bias_type", name="uq_user_quest_biases_scope"
        ),
        Index("idx_user_quest_biases_user", "user_id"),
        CheckConstraint("observations_count >= 0", name="ck_uqb_observations"),
    )
