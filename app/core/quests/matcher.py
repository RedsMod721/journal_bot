"""
Quest matching orchestration for journal entries.

This module provides the QuestMatcher class that coordinates all quest
completion checkers to evaluate journal entries against active quests.

The matcher:
1. Retrieves user's active quests
2. Prepares context from journal entry (content, detected amounts)
3. Runs appropriate checker for each quest type
4. Updates quest progress and emits completion events
"""

import re
from typing import TYPE_CHECKING

from app.core.events import EventBus
from app.core.quests.base import CompletionType
from app.core.quests.checkers import (
    AccumulationChecker,
    FrequencyChecker,
    KeywordMatchChecker,
    YesNoChecker,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.journal_entry import JournalEntry
    from app.models.mission_quest import UserMissionQuest


class QuestMatcher:
    """
    Orchestrates quest completion checking for journal entries.

    Coordinates all quest checkers to evaluate whether journal entries
    satisfy quest completion conditions. Handles progress updates and
    emits events when quests are completed.

    Example:
        from app.core.events import get_event_bus

        matcher = QuestMatcher(get_event_bus())
        updated_quests = matcher.match_journal_entry(db, entry)

        for quest in updated_quests:
            print(f"{quest.name}: {quest.completion_progress}%")
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Initialize the quest matcher.

        Args:
            event_bus: EventBus instance for emitting quest events
        """
        self._event_bus = event_bus
        self._checkers = self._register_checkers()

    def match_journal_entry(
        self,
        db: "Session",
        entry: "JournalEntry",
    ) -> list["UserMissionQuest"]:
        """
        Match a journal entry against user's active quests.

        Args:
            db: Database session
            entry: The journal entry to evaluate

        Returns:
            List of quests that were updated (progress changed or completed)
        """
        from app.models.mission_quest import UserMissionQuest

        active_quests = (
            db.query(UserMissionQuest)
            .filter(
                UserMissionQuest.user_id == entry.user_id,
                UserMissionQuest.status == "in_progress",
            )
            .all()
        )

        context = self._prepare_context(entry)
        updated_quests: list[UserMissionQuest] = []

        for quest in active_quests:
            was_updated = self._check_quest(db, quest, context)
            if was_updated:
                updated_quests.append(quest)

        return updated_quests

    def _check_quest(
        self,
        db: "Session",
        quest: "UserMissionQuest",
        context: dict,
    ) -> bool:
        """
        Check a single quest against the context.

        Args:
            db: Database session
            quest: The quest to check
            context: Context dict from journal entry

        Returns:
            True if quest was updated, False otherwise
        """
        completion_type = self._get_quest_completion_type(quest)
        checker = self._checkers.get(completion_type)

        if checker is None:
            return False

        old_progress = quest.completion_progress
        old_status = quest.status

        try:
            is_complete, new_progress = checker.check_completion(db, quest, context)
        except Exception:
            return False

        if new_progress == old_progress and not is_complete:
            return False

        quest.completion_progress = new_progress

        if is_complete and old_status != "completed":
            quest.complete()
            self._emit_quest_completed(quest)
        elif new_progress != old_progress:
            self._emit_progress_updated(quest)

        return True

    def _prepare_context(self, entry: "JournalEntry") -> dict:
        """
        Prepare context dict from a journal entry.

        Extracts:
        - journal_content: The entry text
        - journal_entry_id: The entry UUID
        - detected amounts (minutes, count, hours, etc.)
        - manual_completion flag from AI categories

        Args:
            entry: The journal entry to extract context from

        Returns:
            Context dict for checkers
        """
        context: dict = {
            "journal_content": entry.content,
            "journal_entry_id": entry.id,
            "journal_created_at": entry.created_at,
        }

        amounts = self._detect_amounts(entry.content)
        for key, value in amounts.items():
            context[f"detected_{key}"] = value

        ai_categories = entry.ai_categories or {}
        if ai_categories.get("manual_completion"):
            context["manual_completion"] = True

        if "detected_keywords" in ai_categories:
            context["detected_keywords"] = ai_categories["detected_keywords"]

        return context

    def _detect_amounts(self, content: str) -> dict:
        """
        Detect numeric amounts in journal content.

        Patterns detected:
        - "45 minutes", "1 hour", "2 hours"
        - "3 times", "5 reps"
        - "10 pages", "2 chapters"
        - "5 km", "3 miles"

        Args:
            content: The journal text to analyze

        Returns:
            Dict mapping unit types to detected values
        """
        amounts: dict = {}
        content_lower = content.lower()

        patterns = [
            (r"(\d+(?:\.\d+)?)\s*(?:minute|min)s?", "minutes"),
            (r"(\d+(?:\.\d+)?)\s*hours?", "hours"),
            (r"(\d+)\s*times?", "count"),
            (r"(\d+)\s*reps?", "count"),
            (r"(\d+)\s*pages?", "pages"),
            (r"(\d+)\s*chapters?", "chapters"),
            (r"(\d+(?:\.\d+)?)\s*(?:km|kilometers?|kilometres?)", "km"),
            (r"(\d+(?:\.\d+)?)\s*miles?", "miles"),
            (r"(\d+)\s*steps?", "steps"),
            (r"(\d+)\s*calories?", "calories"),
        ]

        for pattern, unit in patterns:
            match = re.search(pattern, content_lower)
            if match:
                value = match.group(1)
                if "." in value:
                    amounts[unit] = float(value)
                else:
                    amounts[unit] = int(value)

        if "hours" in amounts and "minutes" not in amounts:
            amounts["minutes"] = int(amounts["hours"] * 60)

        return amounts

    def _get_quest_completion_type(self, quest: "UserMissionQuest") -> str:
        """
        Get the completion type for a quest.

        Args:
            quest: The quest to get completion type for

        Returns:
            Completion type string (defaults to "yes_no")
        """
        if quest.template and quest.template.completion_condition:
            return quest.template.completion_condition.get("type", "yes_no")
        return "yes_no"

    def _register_checkers(self) -> dict:
        """
        Register all checkers by completion type.

        Returns:
            Dict mapping completion type strings to checker instances
        """
        return {
            CompletionType.YES_NO.value: YesNoChecker(),
            CompletionType.ACCUMULATION.value: AccumulationChecker(),
            CompletionType.FREQUENCY.value: FrequencyChecker(),
            CompletionType.KEYWORD_MATCH.value: KeywordMatchChecker(),
            "yes_no": YesNoChecker(),
            "accumulation": AccumulationChecker(),
            "frequency": FrequencyChecker(),
            "keyword_match": KeywordMatchChecker(),
        }

    def _emit_quest_completed(self, quest: "UserMissionQuest") -> None:
        """Emit quest.completed event."""
        reward_xp = 0
        reward_coins = 0

        if quest.template:
            reward_xp = quest.template.reward_xp
            reward_coins = quest.template.reward_coins

        self._event_bus.emit(
            "quest.completed",
            {
                "user_id": quest.user_id,
                "quest_id": quest.id,
                "quest_name": quest.name,
                "reward_xp": reward_xp,
                "reward_coins": reward_coins,
            },
        )

    def _emit_progress_updated(self, quest: "UserMissionQuest") -> None:
        """Emit quest.progress_updated event."""
        self._event_bus.emit(
            "quest.progress_updated",
            {
                "user_id": quest.user_id,
                "quest_id": quest.id,
                "progress": quest.completion_progress,
                "target": quest.completion_target,
            },
        )
