"""Strategy tracking table.

One row per user. Stores rolling 30-day strategy counts, computed variety
metrics, window boundaries, and per-strategy streak state for diminishing
returns (architecture §2 table 31, §5.2–5.3).
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


class StrategyTracking(Base):
    __tablename__ = "strategy_tracking"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # ------------------------------------------------------------------
    # Rolling 30-day strategy counts (architecture §5.2, table 31)
    # ------------------------------------------------------------------
    social_risk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    study_burst_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mundane_focus_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    troll_exploits_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_grind_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    harmony_balance_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ------------------------------------------------------------------
    # Diminishing-returns streak state (architecture §5.9)
    # JSON: {strategy_key: {count: int, last_day: "YYYY-MM-DD"}}
    # ------------------------------------------------------------------
    strategy_streaks_json: Mapped[str] = mapped_column(
        String, nullable=False, default="{}"
    )

    # ------------------------------------------------------------------
    # Computed variety metrics (architecture §5.3)
    # Persisted so the dashboard can read without recalculating.
    # Base formula: variety_bonus_pct = score² × 0.30 (max 0.30).
    # DB constraint allows up to 0.60 to accommodate Harvest Festival
    # event doubling (story arc — applied by event system, not this step).
    # ------------------------------------------------------------------
    variety_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    variety_bonus_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ------------------------------------------------------------------
    # Rolling window boundaries (architecture §5.0.4)
    # ------------------------------------------------------------------
    window_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    window_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_strategy_tracking_user_id"),
        Index("idx_strategy_tracking_user", "user_id"),
        CheckConstraint(
            "social_risk_count >= 0", name="ck_strategy_tracking_social_risk_count"
        ),
        CheckConstraint(
            "study_burst_count >= 0", name="ck_strategy_tracking_study_burst_count"
        ),
        CheckConstraint(
            "mundane_focus_count >= 0",
            name="ck_strategy_tracking_mundane_focus_count",
        ),
        CheckConstraint(
            "troll_exploits_count >= 0",
            name="ck_strategy_tracking_troll_exploits_count",
        ),
        CheckConstraint(
            "daily_grind_count >= 0", name="ck_strategy_tracking_daily_grind_count"
        ),
        CheckConstraint(
            "harmony_balance_count >= 0",
            name="ck_strategy_tracking_harmony_balance_count",
        ),
        CheckConstraint(
            "variety_score IS NULL OR (variety_score >= 0 AND variety_score <= 1.0)",
            name="ck_strategy_tracking_variety_score",
        ),
        CheckConstraint(
            "variety_bonus_pct IS NULL OR"
            " (variety_bonus_pct >= 0 AND variety_bonus_pct <= 0.60)",
            name="ck_strategy_tracking_variety_bonus_pct",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyTracking user_id={self.user_id!r} "
            f"variety_score={self.variety_score}>"
        )
