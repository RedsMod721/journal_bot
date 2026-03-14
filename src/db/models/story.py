"""Story arc tables (Section 8).

story_arcs  — time-bounded narrative modes that modify system behaviour.
arc_triggers — immutable audit log of events that created / transitioned arcs.

Multipliers are stored as basis points (integer) so arithmetic stays in the
integer domain and avoids floating-point drift:
    10 000 bp = 1.0×  (neutral / no effect)
     5 000 bp = 0.5×
    15 000 bp = 1.5×

Timestamps are RFC3339 UTC strings with exactly 3 millisecond digits
(Section 8.2.1).  Use src.core.arc_timestamps.now_utc_fixed_ms() to generate
them consistently.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.user import User


class StoryArc(Base):
    __tablename__ = "story_arcs"

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # ------------------------------------------------------------------ #
    # Classification                                                       #
    # ------------------------------------------------------------------ #
    arc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # "active" | "paused" | "completed" | "abandoned"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # Required when arc_type = 'event'; NULL otherwise (enforced by CHECK)
    event_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # JSON array of theme UUIDs, sorted ascending; NULL = no theme filter
    theme_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------ #
    # Multipliers (basis points; 10 000 bp = 1.0×)                        #
    # ------------------------------------------------------------------ #
    xp_requirement_multiplier_bp: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10000
    )
    xp_reward_multiplier_bp: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10000
    )
    decay_rate_multiplier_bp: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10000
    )

    # ------------------------------------------------------------------ #
    # Lifecycle timestamps — fixed-ms RFC3339 UTC (Section 8.2.1)         #
    # ------------------------------------------------------------------ #
    started_at: Mapped[str] = mapped_column(String(30), nullable=False)
    duration_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[str] = mapped_column(String(30), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(30), nullable=False)
    # Set for both 'completed' and 'abandoned' terminal states
    completed_at: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys="StoryArc.user_id",
        back_populates="story_arcs",
    )
    triggers: Mapped[list["ArcTrigger"]] = relationship(
        "ArcTrigger",
        back_populates="arc",
        cascade="all, delete-orphan",
    )

    # ------------------------------------------------------------------ #
    # Constraints & indexes                                                #
    # ------------------------------------------------------------------ #
    __table_args__ = (
        CheckConstraint(
            "arc_type IN ('tutorial', 'regression', 'redemption', 'event')",
            name="ck_story_arcs_arc_type",
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'abandoned')",
            name="ck_story_arcs_status",
        ),
        CheckConstraint(
            "(arc_type = 'event' AND event_name IS NOT NULL)"
            " OR (arc_type != 'event' AND event_name IS NULL)",
            name="ck_story_arcs_event_name",
        ),
        CheckConstraint(
            "xp_requirement_multiplier_bp > 0",
            name="ck_story_arcs_xp_req_bp",
        ),
        CheckConstraint(
            "xp_reward_multiplier_bp > 0",
            name="ck_story_arcs_xp_reward_bp",
        ),
        CheckConstraint(
            "decay_rate_multiplier_bp >= 0",
            name="ck_story_arcs_decay_bp",
        ),
        Index("idx_story_arcs_user", "user_id"),
        Index("idx_story_arcs_status", "status"),
        # idx_story_arcs_active_unique (partial) is created by migration MB84
        # because DDL for partial unique indexes is dialect-specific.
    )

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @property
    def theme_ids_list(self) -> list[str]:
        """Return theme_ids column as a parsed list (empty list if NULL)."""
        if not self.theme_ids:
            return []
        try:
            return json.loads(self.theme_ids)
        except (ValueError, TypeError):
            return []

    @theme_ids_list.setter
    def theme_ids_list(self, value: list[str] | None) -> None:
        """Persist a list of theme UUIDs, sorted ascending."""
        if value:
            self.theme_ids = json.dumps(sorted(value), separators=(",", ":"))
        else:
            self.theme_ids = None

    @property
    def xp_requirement_multiplier(self) -> float:
        """Basis-points → float convenience accessor."""
        return self.xp_requirement_multiplier_bp / 10_000

    @property
    def xp_reward_multiplier(self) -> float:
        """Basis-points → float convenience accessor."""
        return self.xp_reward_multiplier_bp / 10_000

    @property
    def decay_rate_multiplier(self) -> float:
        """Basis-points → float convenience accessor."""
        return self.decay_rate_multiplier_bp / 10_000

    def __repr__(self) -> str:
        return (
            f"<StoryArc id={self.id!r} arc_type={self.arc_type!r}"
            f" status={self.status!r}>"
        )


class ArcTrigger(Base):
    __tablename__ = "arc_triggers"

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    arc_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("story_arcs.id", ondelete="CASCADE"), nullable=False
    )

    # ------------------------------------------------------------------ #
    # Trigger payload                                                      #
    # ------------------------------------------------------------------ #
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Applicable to regression / recovery triggers; NULL for manual / system
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Arbitrary JSON metadata (anomaly scores, thresholds, etc.)
    trigger_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Fixed-ms RFC3339 UTC (Section 8.2.1)
    triggered_at: Mapped[str] = mapped_column(String(30), nullable=False)

    # ------------------------------------------------------------------ #
    # Relationships                                                        #
    # ------------------------------------------------------------------ #
    user: Mapped["User"] = relationship("User", back_populates="arc_triggers")
    arc: Mapped["StoryArc"] = relationship("StoryArc", back_populates="triggers")

    # ------------------------------------------------------------------ #
    # Constraints & indexes                                                #
    # ------------------------------------------------------------------ #
    __table_args__ = (
        CheckConstraint(
            "confidence_score IS NULL"
            " OR (confidence_score >= 0.0 AND confidence_score <= 1.0)",
            name="ck_arc_triggers_confidence",
        ),
        Index("idx_arc_triggers_arc", "arc_id"),
        Index("idx_arc_triggers_type", "trigger_type"),
        Index("idx_arc_triggers_user", "user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ArcTrigger id={self.id!r} trigger_type={self.trigger_type!r}"
            f" arc_id={self.arc_id!r}>"
        )
