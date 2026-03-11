"""
SQLAlchemy model for XP awards.

Table:
    xp_awards — every XP event awarded to a skill or theme, with full
                 audit trail and Section 10/13 idempotency support.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.quest import Quest
    from src.db.models.skill import Skill, Theme
    from src.db.models.user import User


class XpAward(Base):
    """
    Immutable record of a single XP award to a skill or theme.

    Every time the AI pipeline awards XP it writes one row here. The row is
    the source of truth for audit, replay, and idempotency checking.

    Target constraint:
        Either `skill_id` OR `theme_id` must be non-null, never both and
        never neither. Enforced by the CHECK constraint below.

    Idempotency (Section 10 / Section 13 v2):
        `award_identity_key` is a canonical stable hash of the award.
        The UNIQUE partial index `uq_xp_awards_identity` prevents duplicate
        awards for the same identity key. Legacy write paths that predate
        Section 13 v2 may leave `award_identity_key` NULL.

    Composite FKs:
        All child FKs are user-scoped to prevent cross-tenant data leakage.

    Distribution types:
        primary   — awarded directly to the primary skill of the quest
        secondary — awarded to a secondary contributing skill
        theme     — awarded to a theme via skill→theme propagation (Q22)
    """

    __tablename__ = "xp_awards"

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

    # ------------------------------------------------------------------
    # Idempotency / audit fields
    # ------------------------------------------------------------------
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # Stable reason key, e.g. 'quest_complete', 'bonus_insight', 'arc_bonus'
    xp_reason: Mapped[str] = mapped_column(String(100), nullable=False)
    processing_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # Section 10 canonical stable identity hash (required for Section 13 v2)
    award_identity_key: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    ruleset_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    pipeline_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # ------------------------------------------------------------------
    # Target — skill XOR theme (CHECK constraint enforced below)
    # ------------------------------------------------------------------
    skill_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    theme_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Source quest — composite FK in __table_args__
    quest_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # ------------------------------------------------------------------
    # Amount & distribution
    # ------------------------------------------------------------------
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    distribution_type: Mapped[str] = mapped_column(String(20), nullable=False)
    skill_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ------------------------------------------------------------------
    # Q22 EXTRA: Theme propagation tracking
    # ------------------------------------------------------------------
    # Which skill triggered this theme XP award
    source_skill_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    # How much XP the source skill gained (to derive the 1% theme share)
    source_skill_xp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    awarded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship("User", back_populates="xp_awards")
    skill: Mapped[Optional["Skill"]] = relationship(
        "Skill",
        back_populates="xp_awards",
        viewonly=True,
        primaryjoin="and_(XpAward.user_id == Skill.user_id, XpAward.skill_id == Skill.id)",
        foreign_keys=[user_id, skill_id],
    )
    theme: Mapped[Optional["Theme"]] = relationship(
        "Theme",
        back_populates="xp_awards",
        viewonly=True,
        primaryjoin="and_(XpAward.user_id == Theme.user_id, XpAward.theme_id == Theme.id)",
        foreign_keys=[user_id, theme_id],
    )
    quest: Mapped["Quest"] = relationship(
        "Quest",
        back_populates="xp_awards",
        viewonly=True,
        primaryjoin="and_(XpAward.user_id == Quest.user_id, XpAward.quest_id == Quest.id)",
        foreign_keys=[user_id, quest_id],
    )

    __table_args__ = (
        # Composite FK: entry belongs to same user
        ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_xp_awards_user_entry",
        ),
        # Composite FK: quest belongs to same user
        ForeignKeyConstraint(
            ["user_id", "quest_id"],
            ["quests.user_id", "quests.id"],
            ondelete="CASCADE",
            name="fk_xp_awards_user_quest",
        ),
        # Composite FK: target skill belongs to same user (nullable)
        ForeignKeyConstraint(
            ["user_id", "skill_id"],
            ["skills.user_id", "skills.id"],
            ondelete="CASCADE",
            name="fk_xp_awards_user_skill",
        ),
        # Composite FK: target theme belongs to same user (nullable)
        ForeignKeyConstraint(
            ["user_id", "theme_id"],
            ["themes.user_id", "themes.id"],
            ondelete="CASCADE",
            name="fk_xp_awards_user_theme",
        ),
        # Composite FK: source_skill belongs to same user (nullable, SET NULL)
        ForeignKeyConstraint(
            ["user_id", "source_skill_id"],
            ["skills.user_id", "skills.id"],
            ondelete="SET NULL",
            name="fk_xp_awards_user_source_skill",
        ),
        # Canonical idempotency index (partial — only when key is populated)
        UniqueConstraint(
            "user_id",
            "award_identity_key",
            name="uq_xp_awards_identity",
        ),
        Index("idx_xp_awards_user", "user_id"),
        Index("idx_xp_awards_entry", "user_id", "entry_id"),
        Index("idx_xp_awards_user_skill", "user_id", "skill_id"),
        Index("idx_xp_awards_user_theme", "user_id", "theme_id"),
        Index("idx_xp_awards_quest", "user_id", "quest_id"),
        Index("idx_xp_awards_reason", "user_id", "xp_reason"),
        Index("idx_xp_awards_ruleset_version", "user_id", "ruleset_version"),
        Index("idx_xp_awards_processing_run", "user_id", "processing_run_id"),
        CheckConstraint("amount > 0", name="ck_xp_awards_amount"),
        CheckConstraint(
            "distribution_type IN ('primary','secondary','theme')",
            name="ck_xp_awards_distribution_type",
        ),
        CheckConstraint(
            "skill_weight IS NULL OR (skill_weight >= 0 AND skill_weight <= 1.0)",
            name="ck_xp_awards_skill_weight",
        ),
        # Exactly one of skill_id / theme_id must be set
        CheckConstraint(
            "(skill_id IS NOT NULL AND theme_id IS NULL) OR "
            "(skill_id IS NULL AND theme_id IS NOT NULL)",
            name="ck_xp_awards_target_xor",
        ),
    )

    def __repr__(self) -> str:
        target = (
            f"skill={self.skill_id!r}" if self.skill_id else f"theme={self.theme_id!r}"
        )
        return f"<XpAward id={self.id!r} amount={self.amount} {target}>"
