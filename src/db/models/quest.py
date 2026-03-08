"""
SQLAlchemy models for the quest system.

Tables:
    quest_templates       — global reusable quest catalog (no user_id)
    quests                — user's active / historical quests
    quest_failure_tracker — per-user, per-quest-type failure counts (Q23)
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
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.journal_entry import JournalEntry
    from src.db.models.skill import Skill
    from src.db.models.user import User
    from src.db.models.xp import XpAward


class QuestTemplate(Base):
    """
    Global quest template catalog shared across all users.

    Templates define reusable quest blueprints (e.g. "Run 5 km", "Code for
    30 min"). Individual user quests may reference a template via `template_id`.

    Scope: global in MVP — no `user_id`. Post-MVP may add `owner_user_id`
    for user-defined templates.
    """

    __tablename__ = "quest_templates"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Thematic category: fitness, learning, social, maintenance, etc.
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    completion_type: Mapped[str] = mapped_column(String(20), nullable=False)
    base_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=480)
    estimated_duration_minutes: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # JSON: {"distance": "5km", "duration": "30min"}
    parameters: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    quests: Mapped[list["Quest"]] = relationship("Quest", back_populates="template")

    __table_args__ = (
        Index("idx_quest_templates_category", "category"),
        Index("idx_quest_templates_usage", "usage_count"),
        CheckConstraint(
            "completion_type IN ('one_time','cumulative','recursive','streak')",
            name="ck_quest_templates_completion_type",
        ),
        CheckConstraint("base_xp > 0", name="ck_quest_templates_base_xp"),
    )

    def __repr__(self) -> str:
        return f"<QuestTemplate id={self.id!r} name={self.name!r}>"


class Quest(Base):
    """
    A user's quest — either instant (single-session) or long-term.

    Quest lifecycle: active → completed | failed | expired | abandoned

    Key design points:
        - `quest_type` (instant|longterm) is the physical scope enum.
          Section 10's conceptual `quest_scope` maps to this column.
        - `template_quest_type` holds the Section 10 v8 template/streak
          identity key — distinct from the scope enum above.
        - `semantic_key` / `successor_key` / `instance_key` are used by the
          deterministic quest matcher (Section 10 v8) for idempotent creation.
        - `failure_badge` / `attempt_number` implement Q23 graduated penalties.
        - `confidence_score` feeds the Q27 learning system.

    Epoch-ms timestamps (created_at_utc_ms etc.) are stored alongside RFC3339
    timestamps for Section 10 v8 compatibility.

    Composite FK:
        (user_id, skill_id) → (skills.user_id, skills.id)
        Ensures a quest can only reference a skill that belongs to the same user.
    """

    __tablename__ = "quests"

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
    # Source entry that triggered this quest (SET NULL on entry delete)
    entry_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Template this quest was generated from
    template_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("quest_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Primary skill — composite FK enforced in __table_args__
    skill_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # ------------------------------------------------------------------
    # Quest details
    # ------------------------------------------------------------------
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # Physical scope: 'instant' or 'longterm'
    quest_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Section 10 v8 template/streak identity key (distinct from quest_type)
    template_quest_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    completion_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # ------------------------------------------------------------------
    # Section 10 v8 deterministic matcher keys
    # ------------------------------------------------------------------
    source_local_date: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True  # YYYY-MM-DD, required for instant quests
    )
    semantic_key: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True  # Required for streak identity
    )
    successor_key: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True  # Required for recursive successor identity
    )
    instance_key: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True  # When max_active > 1 for template-based quests
    )
    created_from_entry_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True  # Nullable legacy; Section 10 v8 decision determinism
    )
    # Confidence in basis-points (0–10000 = 0%–100%)
    creation_confidence_bp: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # ------------------------------------------------------------------
    # XP calculation
    # ------------------------------------------------------------------
    base_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=480)
    final_xp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ------------------------------------------------------------------
    # Q23: Failure tracking
    # ------------------------------------------------------------------
    failure_badge: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True  # e.g. "Attempted", "Attempted (2×)"
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ------------------------------------------------------------------
    # Status & progress
    # ------------------------------------------------------------------
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    current_progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required_progress: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ------------------------------------------------------------------
    # Timestamps (RFC3339 + Section 10 v8 epoch-ms)
    # ------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    created_at_utc_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at_utc_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at_utc_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at_utc_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    due_at_utc_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expired_at_utc_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship("User", back_populates="quests")
    entry: Mapped[Optional["JournalEntry"]] = relationship(
        "JournalEntry",
        foreign_keys=[entry_id],
    )
    template: Mapped[Optional["QuestTemplate"]] = relationship(
        "QuestTemplate",
        back_populates="quests",
    )
    skill: Mapped["Skill"] = relationship(
        "Skill",
        viewonly=True,
        primaryjoin="and_(Quest.user_id == Skill.user_id, Quest.skill_id == Skill.id)",
        foreign_keys=[user_id, skill_id],
    )
    xp_awards: Mapped[list["XpAward"]] = relationship(
        "XpAward",
        back_populates="quest",
        viewonly=True,
        primaryjoin="and_(Quest.user_id == XpAward.user_id, Quest.id == XpAward.quest_id)",
        foreign_keys="[XpAward.user_id, XpAward.quest_id]",
    )

    __table_args__ = (
        # Composite FK: skill must belong to the same user
        ForeignKeyConstraint(
            ["user_id", "skill_id"],
            ["skills.user_id", "skills.id"],
            ondelete="CASCADE",
            name="fk_quests_user_skill",
        ),
        UniqueConstraint("user_id", "id", name="uq_quests_user_id"),
        Index("idx_quests_user", "user_id"),
        Index("idx_quests_user_status", "user_id", "status"),
        Index("idx_quests_user_skill", "user_id", "skill_id"),
        Index("idx_quests_user_created", "user_id", "created_at"),
        Index("idx_quests_user_entry", "user_id", "entry_id"),
        Index("idx_quests_user_updated_ms", "user_id", "updated_at_utc_ms", "id"),
        CheckConstraint(
            "quest_type IN ('instant','longterm')",
            name="ck_quests_quest_type",
        ),
        CheckConstraint(
            "completion_type IN ('one_time','cumulative','recursive','streak')",
            name="ck_quests_completion_type",
        ),
        CheckConstraint(
            "status IN ('active','completed','failed','expired','abandoned')",
            name="ck_quests_status",
        ),
        CheckConstraint("base_xp > 0", name="ck_quests_base_xp"),
        CheckConstraint("attempt_number >= 1", name="ck_quests_attempt_number"),
        CheckConstraint(
            "creation_confidence_bp IS NULL OR "
            "(creation_confidence_bp >= 0 AND creation_confidence_bp <= 10000)",
            name="ck_quests_creation_confidence_bp",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR "
            "(confidence_score >= 0 AND confidence_score <= 1.0)",
            name="ck_quests_confidence_score",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Quest id={self.id!r} name={self.name!r} "
            f"type={self.quest_type!r} status={self.status!r}>"
        )


class QuestFailureTracker(Base):
    """
    Tracks failure counts per quest-type per user for graduated Q23 penalties.

    Penalty schedule:
        1st failure — 0% XP penalty
        2nd failure — -20% XP penalty
        3rd+ failure — -50% XP penalty + Struggle Arc triggered

    The counter resets on any successful completion of the same quest type.

    UNIQUE(user_id, quest_type) — one row per semantic quest type per user.
    """

    __tablename__ = "quest_failure_tracker"

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
    # Semantic quest type identifier (e.g. "cardio_running", "python_coding")
    quest_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Optional skill scope — composite FK enforced below
    skill_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship("User", back_populates="quest_failure_trackers")

    __table_args__ = (
        # Composite FK: skill must belong to the same user (nullable)
        ForeignKeyConstraint(
            ["user_id", "skill_id"],
            ["skills.user_id", "skills.id"],
            ondelete="SET NULL",
            name="fk_quest_failure_tracker_user_skill",
        ),
        UniqueConstraint(
            "user_id", "quest_type", name="uq_quest_failure_tracker_user_type"
        ),
        Index("idx_failure_tracker_user", "user_id"),
        Index("idx_failure_tracker_user_skill", "user_id", "skill_id"),
        CheckConstraint(
            "failure_count >= 0", name="ck_quest_failure_tracker_failure_count"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<QuestFailureTracker user_id={self.user_id!r} "
            f"quest_type={self.quest_type!r} failures={self.failure_count}>"
        )
