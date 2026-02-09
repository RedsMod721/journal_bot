"""
Concrete implementations of quest completion checkers.

This module provides checkers for various quest completion types:
- YesNoChecker: Binary completion (manual or context-based)

Each checker inherits from QuestCompletionChecker and implements
the check_completion() method to evaluate quest progress.
"""

from typing import TYPE_CHECKING

from app.core.quests.base import QuestCompletionChecker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.mission_quest import UserMissionQuest


class YesNoChecker(QuestCompletionChecker):
    """
    Evaluates binary yes/no quest completion.

    Checks if a quest has been manually marked as complete or if
    the context indicates completion. Used for simple quests like
    "Did you exercise today?" or "Did you read a book?".

    Quest template condition:
        {"type": "yes_no"}

    Context fields:
        - manual_completion: bool - Explicitly marks quest as complete
        - quest_completed: bool - Completion flag
        - quest_complete: bool - Legacy completion flag
        - completed: bool - Alternative completion flag
        - is_complete: bool - Alternative completion flag

    Example:
        user_quest = UserMissionQuest(name="Did you exercise today?")
        context = {"manual_completion": True}
        is_complete, progress = checker.check_completion(db, user_quest, context)
        # Returns: (True, 100)
    """

    def check_completion(
        self,
        db: "Session",
        user_quest: "UserMissionQuest",
        context: dict,
    ) -> tuple[bool, int]:
        """
        Check if a yes/no quest has been completed.

        Args:
            db: Database session (unused for yes/no checks)
            user_quest: The user's quest instance
            context: Dict containing completion flags

        Returns:
            (True, 100) if complete, (False, current_progress) otherwise
        """
        if context.get("manual_completion") is True:
            return (True, 100)

        if user_quest.status == "completed":
            return (True, 100)

        if context.get("quest_completed") is True:
            return (True, 100)

        if context.get("quest_complete") is True:
            return (True, 100)

        if context.get("completed") is True:
            return (True, 100)

        if context.get("is_complete") is True:
            return (True, 100)

        return (False, user_quest.completion_progress)
