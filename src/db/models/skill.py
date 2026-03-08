"""
SQLAlchemy models for skill and theme progression.

Tables:
    skills               — user skills that level up through XP
    themes               — 12 broad life themes (progress ~1000x slower)
    skill_theme_mappings — many-to-many between skills and themes (Q22)
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
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
    from src.db.models.user import User
    from src.db.models.xp import XpAward

# Valid rank progression order
_RANK_ENUM = "rank IN ('F','E','D','C','B','A','S','SS','SSS')"

# The 12 core life themes (fixed set — do not extend without a migration)
_THEME_NAMES = (
    "'Physical','Mental','Professional','Social',"
    "'Creative','Emotional','Practical','Intellectual',"
    "'Spiritual','Adventure','Discipline','Rest'"
)


class Skill(Base):
    """
    A user skill that grows through XP and levels up.

    Rank progression: F → E → D → C → B → A → S → SS → SSS
    XP curve exponents: 1.5 (F-A), 1.6 (S), 1.8 (SS), 2.0 (SSS)

    Decay:
        `staleness` (0.0–1.0) increases daily when the skill is inactive.
        `decay_paused` prevents staleness from accumulating (e.g. injury).
        Decay rates are controlled by the user's ForgivenessConfig.

    Multi-tenant isolation:
        UNIQUE(user_id, id) enables composite FK references from quests,
        xp_awards, and skill_theme_mappings.
        UNIQUE(user_id, canonical_name) prevents duplicate skills per user.

    Q35 branching (post-MVP):
        `is_specialist_track` and `branch_unlocked_at` are reserved fields.

    Global KB link:
        `global_skill_id` links to the shared knowledge base (added later).
    """

    __tablename__ = "skills"

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
    # Skill identity
    # ------------------------------------------------------------------
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Normalised form used for duplicate detection (lowercase, no spaces)
    canonical_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------
    # Progression
    # ------------------------------------------------------------------
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rank: Mapped[str] = mapped_column(String(3), nullable=False, default="F")
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ------------------------------------------------------------------
    # Decay tracking
    # ------------------------------------------------------------------
    staleness: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    decay_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ------------------------------------------------------------------
    # Q35: Post-MVP specialist branching
    # ------------------------------------------------------------------
    is_specialist_track: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    branch_unlocked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    # ------------------------------------------------------------------
    # Global KB link (nullable — populated when skill is matched to KB)
    # ------------------------------------------------------------------
    global_skill_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("global_skills.id", ondelete="SET NULL"),
        nullable=True,
    )

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

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship("User", back_populates="skills")
    # viewonly: composite FK relationships share user_id with other relationships;
    # DB-level ON DELETE CASCADE handles actual deletion.
    theme_mappings: Mapped[list["SkillThemeMapping"]] = relationship(
        "SkillThemeMapping",
        back_populates="skill",
        viewonly=True,
        primaryjoin="and_(Skill.user_id == SkillThemeMapping.user_id, Skill.id == SkillThemeMapping.skill_id)",
        foreign_keys="[SkillThemeMapping.user_id, SkillThemeMapping.skill_id]",
    )
    xp_awards: Mapped[list["XpAward"]] = relationship(
        "XpAward",
        back_populates="skill",
        viewonly=True,
        primaryjoin="and_(Skill.user_id == XpAward.user_id, Skill.id == XpAward.skill_id)",
        foreign_keys="[XpAward.user_id, XpAward.skill_id]",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_skills_user_id"),
        UniqueConstraint(
            "user_id", "canonical_name", name="uq_skills_user_canonical_name"
        ),
        Index("idx_skills_user", "user_id"),
        Index("idx_skills_user_level", "user_id", "level"),
        Index("idx_skills_user_rank", "user_id", "rank"),
        Index("idx_skills_user_canonical", "user_id", "canonical_name"),
        Index("idx_skills_last_activity", "user_id", "last_activity_at"),
        CheckConstraint("level >= 1", name="ck_skills_level"),
        CheckConstraint(_RANK_ENUM, name="ck_skills_rank"),
        CheckConstraint("xp >= 0", name="ck_skills_xp"),
        CheckConstraint(
            "staleness >= 0 AND staleness <= 1.0",
            name="ck_skills_staleness",
        ),
    )

    def __repr__(self) -> str:
        return f"<Skill id={self.id!r} name={self.name!r} rank={self.rank!r} level={self.level}>"


class Theme(Base):
    """
    One of 12 broad life themes assigned to every user on signup.

    Themes gain XP at 0.1% of the XP awarded to any linked skill
    (minimum 1 XP per award). They use the same rank/level curve as
    skills but progress roughly 1000× slower by design.

    The 12 fixed theme names are enforced by a CHECK constraint.

    Multi-tenant isolation:
        UNIQUE(user_id, id) and UNIQUE(user_id, name) prevent duplicates.
    """

    __tablename__ = "themes"

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

    name: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Progression — same curve as skills
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rank: Mapped[str] = mapped_column(String(3), nullable=False, default="F")
    xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

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
    user: Mapped["User"] = relationship("User", back_populates="themes")
    skill_mappings: Mapped[list["SkillThemeMapping"]] = relationship(
        "SkillThemeMapping",
        back_populates="theme",
        viewonly=True,
        primaryjoin="and_(Theme.user_id == SkillThemeMapping.user_id, Theme.id == SkillThemeMapping.theme_id)",
        foreign_keys="[SkillThemeMapping.user_id, SkillThemeMapping.theme_id]",
    )
    xp_awards: Mapped[list["XpAward"]] = relationship(
        "XpAward",
        back_populates="theme",
        viewonly=True,
        primaryjoin="and_(Theme.user_id == XpAward.user_id, Theme.id == XpAward.theme_id)",
        foreign_keys="[XpAward.user_id, XpAward.theme_id]",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_themes_user_id"),
        UniqueConstraint("user_id", "name", name="uq_themes_user_name"),
        Index("idx_themes_user", "user_id"),
        Index("idx_themes_user_level", "user_id", "level"),
        CheckConstraint("level >= 1", name="ck_themes_level"),
        CheckConstraint(_RANK_ENUM, name="ck_themes_rank"),
        CheckConstraint("xp >= 0", name="ck_themes_xp"),
        CheckConstraint(
            f"name IN ({_THEME_NAMES})",
            name="ck_themes_name",
        ),
    )

    def __repr__(self) -> str:
        return f"<Theme id={self.id!r} name={self.name!r} rank={self.rank!r}>"


class SkillThemeMapping(Base):
    """
    Many-to-many mapping between a skill and one or more themes (Q22).

    When a skill gains XP, every theme it is mapped to receives 0.1% of that
    XP (minimum 1 XP). Each theme receives the full 0.1% — the amount is NOT
    split between themes.

    Example:
        Python gains 695 XP → Professional +1 XP, Mental +1 XP, Intellectual +1 XP

    Composite FKs enforce tenant-safe cascade: deleting a skill or theme
    automatically removes its mapping rows.
    """

    __tablename__ = "skill_theme_mappings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(36), nullable=False)
    theme_id: Mapped[str] = mapped_column(String(36), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    skill: Mapped["Skill"] = relationship(
        "Skill",
        back_populates="theme_mappings",
        viewonly=True,
        primaryjoin="and_(SkillThemeMapping.user_id == Skill.user_id, SkillThemeMapping.skill_id == Skill.id)",
        foreign_keys=[user_id, skill_id],
    )
    theme: Mapped["Theme"] = relationship(
        "Theme",
        back_populates="skill_mappings",
        viewonly=True,
        primaryjoin="and_(SkillThemeMapping.user_id == Theme.user_id, SkillThemeMapping.theme_id == Theme.id)",
        foreign_keys=[user_id, theme_id],
    )

    __table_args__ = (
        # Composite FKs — tenant-safe cascade
        ForeignKeyConstraint(
            ["user_id", "skill_id"],
            ["skills.user_id", "skills.id"],
            ondelete="CASCADE",
            name="fk_skill_theme_mappings_skill",
        ),
        ForeignKeyConstraint(
            ["user_id", "theme_id"],
            ["themes.user_id", "themes.id"],
            ondelete="CASCADE",
            name="fk_skill_theme_mappings_theme",
        ),
        UniqueConstraint(
            "user_id",
            "skill_id",
            "theme_id",
            name="uq_skill_theme_mappings_user_skill_theme",
        ),
        Index("idx_skill_theme_user_skill", "user_id", "skill_id"),
        Index("idx_skill_theme_user_theme", "user_id", "theme_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SkillThemeMapping skill_id={self.skill_id!r} theme_id={self.theme_id!r}>"
        )
