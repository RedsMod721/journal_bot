"""
SQLAlchemy models for the forgiveness / decay system.

Tables:
    forgiveness_configs  — per-user decay presets and rate configuration
    decay_snapshots      — daily staleness snapshots for trend analysis
"""
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.user import User


class ForgivenessConfig(Base):
    """
    Per-user forgiveness system configuration.

    Controls how quickly skills and insights decay when inactive, and defines
    grace periods before decay begins. One row per user (UNIQUE on user_id).

    The `users.forgiveness_config_id` FK points back to this table, creating
    a circular reference resolved via `use_alter=True` on the User side.

    Presets:
        balanced  — moderate decay (default)
        hardcore  — aggressive decay, no grace
        lenient   — slow decay, long grace
        zen       — minimal decay
        adaptive  — dynamically adjusted
        custom    — user-defined rates
    """

    __tablename__ = "forgiveness_configs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Preset selector
    preset: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="balanced",
    )

    # Decay rates (fraction of staleness gained per 24 h, 0.0–1.0)
    skill_decay_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.05)
    insight_decay_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)

    # Grace periods before decay starts (days)
    skill_grace_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    insight_grace_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Staleness fraction at which the system flags a skill as critically decayed
    critical_staleness_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.80
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # --- Relationships ---
    # Navigate from ForgivenessConfig → User via forgiveness_configs.user_id.
    # Not paired with back_populates because the circular FK
    # (users.forgiveness_config_id ↔ forgiveness_configs.user_id) means both
    # sides are many-to-one; SQLAlchemy can't infer direction for back_populates.
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        overlaps="forgiveness_config",
    )

    __table_args__ = (
        CheckConstraint(
            "preset IN ('balanced','hardcore','lenient','zen','adaptive','custom')",
            name="ck_forgiveness_configs_preset",
        ),
        CheckConstraint(
            "skill_decay_rate >= 0 AND skill_decay_rate <= 1.0",
            name="ck_forgiveness_configs_skill_decay_rate",
        ),
        CheckConstraint(
            "insight_decay_rate >= 0 AND insight_decay_rate <= 1.0",
            name="ck_forgiveness_configs_insight_decay_rate",
        ),
        CheckConstraint(
            "critical_staleness_threshold >= 0 AND critical_staleness_threshold <= 1.0",
            name="ck_forgiveness_configs_crit_threshold",
        ),
        Index("idx_forgiveness_configs_user", "user_id"),
    )


class DecaySnapshot(Base):
    """
    Daily snapshot of skill/insight staleness aggregates.

    Created once per day per user by a background job. Used for trend analysis
    and the decay graph in the UI. Individual staleness values are stored as
    JSON maps for compact storage.
    """

    __tablename__ = "decay_snapshots"

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
    # Snapshot date (YYYY-MM-DD stored as string for SQLite compatibility)
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False)

    # Aggregated metrics for the day
    average_skill_staleness: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_insight_staleness: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Count of skills at or near critical staleness at snapshot time
    skills_near_critical: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Per-skill and per-insight staleness maps stored as JSON strings
    # Format: '{"<skill_id>": 0.42, ...}'
    skill_staleness_map: Mapped[str | None] = mapped_column(String, nullable=True)
    insight_staleness_map: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # --- Relationships ---
    user: Mapped["User"] = relationship("User", back_populates="decay_snapshots")

    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_decay_snapshots_user_date"),
        Index("idx_decay_snapshots_user_date", "user_id", "snapshot_date"),
    )
