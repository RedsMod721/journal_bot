"""
SQLAlchemy model for user_skill_states.

Tracks each user's unlock/activation state for skills in the global hierarchy.

State machine:
    locked → discovered → unlocked_hidden → activated

    locked:          Hidden from user, cannot gain XP.
    discovered:      Visible (dimmed), cannot gain XP.
    unlocked_hidden: Hidden, can gain XP when activated.
    activated:       Visible, can gain XP.

Multi-tenant isolation:
    UNIQUE(user_id, id) mirrors the pattern used by skills/themes.
    UNIQUE(user_id, skill_id) prevents duplicate state rows per user-skill pair.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.user import User


class UserSkillState(Base):
    """State record for one (user, global_skill) pair in the skill hierarchy."""

    __tablename__ = "user_skill_states"

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
    # References global_skills.id — the canonical skill in the shared KB
    skill_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("global_skills.id", ondelete="CASCADE"),
        nullable=False,
    )

    # State machine value
    state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="locked",
    )
    # User has explicitly blocked this skill from appearing in quest suggestions
    user_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Transition timestamps (nullable — set when the transition occurs)
    discovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    unlocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # How the skill was discovered ("quest:<id>", "entry:<id>", "manual", …)
    discovery_source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Which parent skill's unlock triggered this skill becoming discoverable
    unlock_parent_skill_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="skill_states")

    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_user_skill_states_user_id"),
        UniqueConstraint("user_id", "skill_id", name="uq_user_skill_states_user_skill"),
        Index("idx_user_skill_states_user", "user_id"),
        Index("idx_user_skill_states_state", "state"),
        Index("idx_user_skill_states_user_state", "user_id", "state"),
        CheckConstraint(
            "state IN ('locked','discovered','unlocked_hidden','activated')",
            name="ck_user_skill_states_state",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<UserSkillState user_id={self.user_id!r} "
            f"skill_id={self.skill_id!r} state={self.state!r}>"
        )
