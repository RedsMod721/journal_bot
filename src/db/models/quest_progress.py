"""Quest progress persistence for long-term quest tracking.

Tables:
    quest_progress                      — one row per quest, progress counters
    quest_progress_contribution_days    — idempotent day ledger (Section 10.5.4)
    quest_progress_contribution_entries — append-only entry audit ledger
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.quest import Quest


class QuestProgress(Base):
    """
    Progress counters for a long-term quest.

    Section 10.8.1 designates `last_progress_local_date` as the source of
    truth for streak expiry checks (YYYY-MM-DD in the user's local timezone).

    Legacy columns kept for backwards compatibility:
        progress_value, streak_current, streak_best, last_progress_date,
        updated_at (DateTime)

    Section 10 v10 additions (MB85):
        required_progress, last_progress_local_date, updated_at_utc_ms
    """

    __tablename__ = "quest_progress"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    quest_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # ------------------------------------------------------------------
    # Progress counters
    # ------------------------------------------------------------------
    # Legacy column — total accumulated units (kept for existing rows)
    progress_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Section 10 v10: current / required pair used by streak/cumulative logic
    required_progress: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Streak counters (legacy; kept for existing rows)
    streak_current: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streak_best: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ------------------------------------------------------------------
    # Date tracking
    # ------------------------------------------------------------------
    # Legacy — kept for existing rows
    last_progress_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # Section 10.8.1 — expiry source of truth (YYYY-MM-DD, user local tz)
    last_progress_local_date: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    # Section 10 epoch-ms timestamp (nullable for rows created before MB85)
    updated_at_utc_ms: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    quest: Mapped["Quest"] = relationship("Quest", back_populates="progress")

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
        CheckConstraint("required_progress >= 1", name="ck_quest_progress_required"),
        CheckConstraint("streak_current >= 0", name="ck_quest_progress_streak_current"),
        CheckConstraint("streak_best >= 0", name="ck_quest_progress_streak_best"),
    )

    def __repr__(self) -> str:
        return (
            f"<QuestProgress quest_id={self.quest_id!r}"
            f" progress={self.progress_value}/{self.required_progress}>"
        )


class QuestContributionDay(Base):
    """
    Idempotent day ledger for streak quests (Section 10.5.4).

    One row per (user, quest, calendar day in user's local timezone).
    The UNIQUE constraint on (user_id, quest_id, contribution_local_date)
    makes inserts naturally idempotent — re-processing the same entry for
    the same day is a safe no-op.
    """

    __tablename__ = "quest_progress_contribution_days"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    quest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # YYYY-MM-DD in the user's local timezone
    contribution_local_date: Mapped[str] = mapped_column(String(10), nullable=False)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    quest: Mapped["Quest"] = relationship("Quest", back_populates="contribution_days")

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_contribution_days_user",
        ),
        ForeignKeyConstraint(
            ["user_id", "quest_id"],
            ["quests.user_id", "quests.id"],
            ondelete="CASCADE",
            name="fk_contribution_days_user_quest",
        ),
        UniqueConstraint(
            "user_id",
            "quest_id",
            "contribution_local_date",
            name="uq_contribution_days_user_quest_date",
        ),
        Index("idx_contribution_days_quest", "quest_id"),
        Index("idx_contribution_days_date", "contribution_local_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<QuestContributionDay quest_id={self.quest_id!r}"
            f" date={self.contribution_local_date!r}>"
        )


class QuestContributionEntry(Base):
    """
    Append-only entry audit ledger for streak / cumulative quests (Section 10.5.4).

    One row per (user, quest, journal entry).  The UNIQUE constraint makes
    multi-processing of the same entry safe — a second pipeline run for the
    same entry cannot double-count progress.
    """

    __tablename__ = "quest_progress_contribution_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    quest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # YYYY-MM-DD in user's local timezone — denormalised for fast expiry queries
    contribution_local_date: Mapped[str] = mapped_column(String(10), nullable=False)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    quest: Mapped["Quest"] = relationship(
        "Quest", back_populates="contribution_entries"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_contribution_entries_user",
        ),
        ForeignKeyConstraint(
            ["user_id", "quest_id"],
            ["quests.user_id", "quests.id"],
            ondelete="CASCADE",
            name="fk_contribution_entries_user_quest",
        ),
        ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_contribution_entries_user_entry",
        ),
        UniqueConstraint(
            "user_id",
            "quest_id",
            "entry_id",
            name="uq_contribution_entries_user_quest_entry",
        ),
        Index("idx_contribution_entries_quest", "quest_id"),
        Index("idx_contribution_entries_entry", "entry_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<QuestContributionEntry quest_id={self.quest_id!r}"
            f" entry_id={self.entry_id!r}>"
        )
