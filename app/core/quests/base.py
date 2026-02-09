"""
Base classes for quest completion checking.

This module defines the Strategy Pattern interface for evaluating quest
completion conditions. Different checkers can implement various completion
logic based on the quest's completion type.

Example usage:
    class AccumulationChecker(QuestCompletionChecker):
        def check_completion(self, db, user_quest, context):
            detected = context.get("detected_minutes", 0)
            new_progress = user_quest.completion_progress + detected
            is_complete = new_progress >= user_quest.completion_target
            return (is_complete, new_progress)

    checker = AccumulationChecker()
    is_complete, progress = checker.check_completion(db, user_quest, context)
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.mission_quest import UserMissionQuest


class CompletionType(Enum):
    """
    Enum of all valid quest completion types.

    Used for validation when processing quest completion conditions.
    Each type corresponds to a specific checker implementation.

    Attributes:
        YES_NO: Simple yes/no completion (e.g., "Did you meditate today?")
        ACCUMULATION: Accumulate progress toward a target (e.g., "Run 50km this month")
        FREQUENCY: Complete action N times (e.g., "Journal 7 days in a row")
        KEYWORD_MATCH: Detect specific keywords in journal content (e.g., "Mention 'gym'")
    """

    YES_NO = "yes_no"
    ACCUMULATION = "accumulation"
    FREQUENCY = "frequency"
    KEYWORD_MATCH = "keyword_match"


class QuestCompletionChecker(ABC):
    """
    Abstract base class for quest completion checkers.

    The Strategy Pattern allows different completion checking algorithms
    to be swapped interchangeably. Each checker evaluates whether a quest
    has been completed based on its specific completion type.

    Checkers might evaluate:
    - Simple yes/no completion from journal content
    - Accumulated progress toward a numeric target
    - Frequency of actions over time
    - Keyword detection in journal entries

    The context dict provides information extracted from the journal entry:
        {
            "journal_content": "Went to gym for 45 minutes",
            "journal_entry_id": "uuid",
            "detected_minutes": 45,
            "detected_keywords": ["gym"]
        }
    """

    @abstractmethod
    def check_completion(
        self,
        db: "Session",
        user_quest: "UserMissionQuest",
        context: dict,
    ) -> tuple[bool, int]:
        """
        Check if a quest has been completed based on the provided context.

        Args:
            db: SQLAlchemy database session for querying related data.
            user_quest: The user's quest instance to check completion for.
            context: Dict containing information from the journal entry.
                    Common fields include:
                    - "journal_content": The raw journal entry text
                    - "journal_entry_id": UUID of the journal entry
                    - "detected_minutes": Extracted duration in minutes
                    - "detected_keywords": List of detected keywords
                    Additional fields may be present depending on the quest type.

        Returns:
            A tuple of (is_complete, new_progress) where:
            - is_complete: True if the quest is now completed, False otherwise
            - new_progress: The updated progress value for the quest

        Raises:
            NotImplementedError: If the subclass does not implement this method.
        """
        raise NotImplementedError("Subclasses must implement check_completion()")
