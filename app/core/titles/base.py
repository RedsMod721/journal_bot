"""
Base classes for title unlock condition evaluation.

This module defines the Strategy Pattern interface for evaluating title
unlock conditions. Different evaluators can implement various condition
checking logic (e.g., streak counting, level thresholds, compound conditions).

Example usage:
    class ThemeLevelEvaluator(ConditionEvaluator):
        def evaluate(self, db, user_id, condition):
            theme = get_theme_by_name(db, user_id, condition["theme"])
            return theme.level >= condition["value"]

    evaluator = ThemeLevelEvaluator()
    unlocked = evaluator.evaluate(db, user_id, {"type": "theme_level", "theme": "Education", "value": 10})
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ConditionType(Enum):
    """
    Enum of all valid unlock condition types.

    Used for validation when processing title unlock conditions.
    Each type corresponds to a specific evaluator implementation.
    """

    # Streak-based conditions
    JOURNAL_STREAK = "journal_streak"

    # Level-based conditions
    THEME_LEVEL = "theme_level"
    SKILL_LEVEL = "skill_level"

    # Entry count conditions
    ENTRY_COUNT = "entry_count"
    MORNING_ENTRIES = "morning_entries"
    NIGHT_ENTRIES = "night_entries"

    # Quest/Mission conditions
    QUEST_COMPLETE = "quest_complete"
    QUESTS_COMPLETED = "quests_completed"
    STORY_ARC_COMPLETE = "story_arc_complete"

    # Resource conditions
    COINS_EARNED = "coins_earned"
    ITEMS_COLLECTED = "items_collected"

    # Social conditions
    SOCIAL_INTERACTIONS = "social_interactions"

    # Logical combination
    COMPOUND = "compound"


class ConditionEvaluator(ABC):
    """
    Abstract base class for title unlock condition evaluators.

    The Strategy Pattern allows different condition evaluation algorithms
    to be swapped interchangeably. Each evaluator checks whether a specific
    type of unlock condition has been met for a user.

    Evaluators might check:
    - Journal entry streaks
    - Theme or skill level thresholds
    - Quest completion counts
    - Time-based entry patterns (morning/night)
    - Compound conditions with AND/OR logic

    The condition dict follows the structure from TitleTemplate.unlock_condition:
        {
            "type": "theme_level",
            "theme": "Education",
            "value": 10
        }
    """

    @abstractmethod
    def evaluate(
        self,
        db: "Session",
        user_id: str,
        condition: dict,
    ) -> bool:
        """
        Evaluate whether a user meets the unlock condition.

        Args:
            db: SQLAlchemy database session for querying user data.
            user_id: The UUID of the user to evaluate.
            condition: Dict containing the condition specification.
                      Structure varies by condition type but always includes:
                      - "type": The condition type (matches ConditionType enum)
                      - Additional fields specific to the condition type

        Returns:
            True if the user meets the condition, False otherwise.

        Raises:
            NotImplementedError: If the subclass does not implement this method.
        """
        raise NotImplementedError("Subclasses must implement evaluate()")
