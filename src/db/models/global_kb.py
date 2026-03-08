"""Global knowledge-base catalog tables."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class GlobalSkill(Base):
    __tablename__ = "global_skills"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_skill_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, unique=True
    )
    canonical_name: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
    )
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    difficulty_baseline: Mapped[str | None] = mapped_column(String(20), nullable=True)
    typical_time_investment_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    xp_per_session_baseline: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_themes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    learning_curve_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_citations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_grade: Mapped[str | None] = mapped_column(String(8), nullable=True)
    evidence_limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    expert_review_priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    contradiction_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contradiction_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contradiction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    hierarchy_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_skill_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        Index("idx_global_skills_source_skill_id", "source_skill_id"),
        Index("idx_global_skills_category", "category"),
        CheckConstraint(
            "expert_review_priority IN (0,1)",
            name="ck_global_skills_expert_review_priority",
        ),
        CheckConstraint(
            "contradiction_flag IN (0,1)", name="ck_global_skills_contradiction_flag"
        ),
        CheckConstraint(
            "typical_time_investment_minutes IS NULL OR "
            "typical_time_investment_minutes >= 0",
            name="ck_global_skills_time_non_negative",
        ),
        CheckConstraint(
            "xp_per_session_baseline IS NULL OR xp_per_session_baseline >= 0",
            name="ck_global_skills_xp_non_negative",
        ),
    )


class GlobalQuest(Base):
    __tablename__ = "global_quests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    quest_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    source_quest_template_id: Mapped[str | None] = mapped_column(
        String(160), nullable=True, unique=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    completion_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    primary_skill_source_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    secondary_skill_source_ids_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    difficulty_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_effort: Mapped[str | None] = mapped_column(String(255), nullable=True)
    xp_reward_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    xp_reward_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cadence_or_target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_citations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_grade: Mapped[str | None] = mapped_column(String(8), nullable=True)
    evidence_limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    expert_review_priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    contradiction_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contradiction_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contradiction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    exploit_risk_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes_for_review: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        Index("idx_global_quests_source_template_id", "source_quest_template_id"),
        Index("idx_global_quests_completion_type", "completion_type"),
        CheckConstraint(
            "completion_type IS NULL OR "
            "completion_type IN ('one_time','cumulative','recursive','streak')",
            name="ck_global_quests_completion_type",
        ),
        CheckConstraint(
            "expert_review_priority IN (0,1)",
            name="ck_global_quests_expert_review_priority",
        ),
        CheckConstraint(
            "contradiction_flag IN (0,1)", name="ck_global_quests_contradiction_flag"
        ),
        CheckConstraint(
            "exploit_risk_flag IN (0,1)", name="ck_global_quests_exploit_risk_flag"
        ),
        CheckConstraint(
            "difficulty_rating IS NULL OR "
            "(difficulty_rating >= 1 AND difficulty_rating <= 10)",
            name="ck_global_quests_difficulty_rating",
        ),
        CheckConstraint(
            "xp_reward_min IS NULL OR xp_reward_min >= 0",
            name="ck_global_quests_xp_reward_min_non_negative",
        ),
        CheckConstraint(
            "xp_reward_max IS NULL OR xp_reward_max >= 0",
            name="ck_global_quests_xp_reward_max_non_negative",
        ),
        CheckConstraint(
            "xp_reward_min IS NULL OR xp_reward_max IS NULL OR xp_reward_min <= xp_reward_max",
            name="ck_global_quests_xp_reward_bounds",
        ),
    )


class GlobalInsight(Base):
    __tablename__ = "global_insights"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    insight_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    source_insight_id: Mapped[str | None] = mapped_column(
        String(160), nullable=True, unique=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    strength_initial: Mapped[float | None] = mapped_column(nullable=True)
    trigger_patterns_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    contraindications_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_citations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_grade: Mapped[str | None] = mapped_column(String(8), nullable=True)
    evidence_limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    expert_review_priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    contradiction_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contradiction_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contradiction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        Index("idx_global_insights_source_id", "source_insight_id"),
        Index("idx_global_insights_category", "category"),
        CheckConstraint(
            "expert_review_priority IN (0,1)",
            name="ck_global_insights_expert_review_priority",
        ),
        CheckConstraint(
            "contradiction_flag IN (0,1)",
            name="ck_global_insights_contradiction_flag",
        ),
        CheckConstraint(
            "strength_initial IS NULL OR "
            "(strength_initial >= 0.0 AND strength_initial <= 1.0)",
            name="ck_global_insights_strength_initial",
        ),
    )


class KbContribution(Base):
    __tablename__ = "kb_contributions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    contribution_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_global_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_kb_contributions_user", "user_id"),
        Index("idx_kb_contributions_status", "status"),
        CheckConstraint(
            "contribution_type IN ('skill','quest','insight','doc')",
            name="ck_kb_contributions_type",
        ),
        CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="ck_kb_contributions_status",
        ),
    )
