"""
Quest learning system.

Implements Section 10.3 (Learning System Q27) from architecture.

Quest kind vocabulary (matches completion_type column):
    'one_time'   — single-event quest (spec calls this 'instant')
    'streak'     — consecutive-day pattern
    'cumulative' — accumulate a total over time (BLOCKED during learning)
    'recursive'  — repeating successor chain (BLOCKED during learning)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from src.db.models.user import User

# Default threshold — user must make this many quest decisions before the
# system considers them past the learning phase.
DEFAULT_QUEST_DECISIONS_THRESHOLD = 20

# Quest kinds that are blocked while learning_phase_complete is False.
_BLOCKED_DURING_LEARNING = frozenset({"cumulative", "recursive"})

# All recognised quest kinds.
_VALID_QUEST_KINDS = frozenset({"one_time", "instant", "streak", "cumulative", "recursive"})


class QuestLearningService:
    """Manage quest learning phase and creation gating (Section 10.3 / Q27)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # 10.3.1: Learning gate
    # ------------------------------------------------------------------

    def check_learning_gate(
        self,
        user: "User",
        quest_kind: str,
    ) -> tuple[bool, str]:
        """
        Check whether the user may create a quest of this kind.

        Section 10.3.1: during the learning phase, cumulative and recursive
        quests are blocked; instant (one_time) and streak quests are allowed.

        Args:
            user:       User model instance.
            quest_kind: 'one_time' | 'instant' | 'streak' | 'cumulative' | 'recursive'

        Returns:
            (allowed, reason_code)
        """
        if user.learning_phase_complete:
            return True, "LEARNING_COMPLETE"

        # During learning phase, block cumulative/recursive.
        if quest_kind in _BLOCKED_DURING_LEARNING:
            return False, "LEARNING_PHASE_BLOCKS_LONGTERM"

        return True, "LEARNING_PHASE_ALLOWS_INSTANT_STREAK"

    # ------------------------------------------------------------------
    # 10.3: Confidence threshold check
    # ------------------------------------------------------------------

    def check_confidence_threshold(
        self,
        user: "User",
        quest_kind: str,
        confidence_score: float,
    ) -> tuple[bool, str]:
        """
        Check whether confidence_score meets the user's threshold for this kind.

        Scores and thresholds are on the 0.0–1.0 scale (matching the DB column).

        Args:
            user:             User model instance.
            quest_kind:       'one_time' | 'instant' | 'streak' | 'cumulative' | 'recursive'
            confidence_score: Float in [0.0, 1.0].

        Returns:
            (meets_threshold, reason_code)
        """
        if quest_kind in ("one_time", "instant"):
            threshold = user.confidence_threshold_instant
            label = "instant"
        elif quest_kind == "streak":
            threshold = user.confidence_threshold_streak
            label = "streak"
        elif quest_kind in ("cumulative", "recursive"):
            threshold = user.confidence_threshold_longterm
            label = "longterm"
        else:
            return False, "UNKNOWN_QUEST_KIND"

        if confidence_score >= threshold:
            return True, f"CONFIDENCE_MEETS_THRESHOLD_{label}"
        return False, f"CONFIDENCE_BELOW_THRESHOLD_{label}"

    # ------------------------------------------------------------------
    # Quest decisions tracking
    # ------------------------------------------------------------------

    def increment_quest_decisions(self, user: "User", count: int = 1) -> None:
        """
        Increment the quest decisions counter by *count*.

        Used to track progress toward learning phase completion.
        Does not auto-complete the learning phase; call
        check_and_complete_learning_phase() separately if desired.
        """
        user.quest_decisions_count += count
        self.db.commit()

    def check_and_complete_learning_phase(
        self,
        user: "User",
        threshold: int = DEFAULT_QUEST_DECISIONS_THRESHOLD,
    ) -> bool:
        """
        Auto-complete the learning phase if the decisions threshold is reached.

        Returns:
            True if the learning phase was just completed, False otherwise
            (already complete, or threshold not yet met).
        """
        if user.learning_phase_complete:
            return False

        if user.quest_decisions_count >= threshold:
            user.learning_phase_complete = True
            self.db.commit()
            return True

        return False

    def mark_learning_complete(self, user: "User") -> None:
        """
        Manually mark the learning phase as complete.

        Allows a user (or admin) to unlock cumulative/recursive quests early.
        No-op if learning is already complete.
        """
        if not user.learning_phase_complete:
            user.learning_phase_complete = True
            self.db.commit()

    # ------------------------------------------------------------------
    # Status summary
    # ------------------------------------------------------------------

    def get_learning_status(self, user: "User") -> dict:
        """
        Return a snapshot of the user's current learning state.

        Returns:
            {
                'learning_complete':            bool,
                'quest_decisions_count':        int,
                'confidence_threshold_instant': float,   # 0.0–1.0
                'confidence_threshold_streak':  float,
                'confidence_threshold_longterm': float,
                'can_create_cumulative':        bool,
                'can_create_recursive':         bool,
            }
        """
        return {
            "learning_complete": user.learning_phase_complete,
            "quest_decisions_count": user.quest_decisions_count,
            "confidence_threshold_instant": user.confidence_threshold_instant,
            "confidence_threshold_streak": user.confidence_threshold_streak,
            "confidence_threshold_longterm": user.confidence_threshold_longterm,
            "can_create_cumulative": user.learning_phase_complete,
            "can_create_recursive": user.learning_phase_complete,
        }
