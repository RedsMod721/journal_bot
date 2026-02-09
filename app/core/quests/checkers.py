"""
Concrete implementations of quest completion checkers.

This module provides checkers for various quest completion types:
- YesNoChecker: Binary completion (manual or context-based)
- AccumulationChecker: Track progress toward a target total
- FrequencyChecker: Complete action X times per period

Each checker inherits from QuestCompletionChecker and implements
the check_completion() method to evaluate quest progress.
"""

from datetime import datetime, timedelta
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app.core.quests.base import QuestCompletionChecker
from app.models.journal_entry import JournalEntry

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


class AccumulationChecker(QuestCompletionChecker):
    """
    Evaluates accumulation-based quest completion.

    Tracks progress toward a target total by accumulating detected
    amounts from journal entries. Used for quests like "Exercise for
    50 minutes total" or "Read 100 pages this month".

    Quest template condition:
        {"type": "accumulation", "target": 50, "unit": "minutes"}

    Supported units and context keys:
        - "minutes" -> context["detected_minutes"]
        - "count" -> context["detected_count"]
        - "pages" -> context["detected_pages"]
        - "hours" -> context["detected_hours"]
        - "km" -> context["detected_km"]
        - "miles" -> context["detected_miles"]
        - Generic: context["detected_{unit}"] or context["detected_amount"]

    Example:
        Quest: "Exercise for 50 minutes total"
        completion_condition = {"type": "accumulation", "target": 50, "unit": "minutes"}
        user_quest.completion_progress = 20

        context = {"detected_minutes": 30}
        is_complete, progress = checker.check_completion(db, user_quest, context)
        # Returns: (True, 50)  # 20 + 30 = 50, target reached
    """

    def check_completion(
        self,
        db: "Session",
        user_quest: "UserMissionQuest",
        context: dict,
    ) -> tuple[bool, int]:
        """
        Check if an accumulation quest has reached its target.

        Args:
            db: Database session (unused for accumulation checks)
            user_quest: The user's quest instance
            context: Dict containing detected amounts

        Returns:
            (is_complete, new_progress) tuple
        """
        condition = self._get_completion_condition(user_quest)
        target = condition.get("target", user_quest.completion_target)
        unit = condition.get("unit", "count")

        detected_amount = self._extract_amount(context, unit)
        new_progress = float(user_quest.completion_progress) + detected_amount

        target_value = float(target)
        is_complete = new_progress >= target_value
        capped_progress = min(new_progress, target_value)

        return (is_complete, int(capped_progress))

    def _get_completion_condition(self, user_quest: "UserMissionQuest") -> dict:
        """Extract completion condition from quest template or return empty dict."""
        if user_quest.template and user_quest.template.completion_condition:
            return user_quest.template.completion_condition
        return {}

    def _extract_amount(self, context: dict, unit: str) -> float:
        """
        Extract the detected amount from context based on unit type.

        Args:
            context: Dict containing detected values
            unit: The unit type to look for

        Returns:
            The detected amount as an integer, or 0 if not found
        """
        unit_key = f"detected_{unit}"
        if unit_key in context:
            try:
                return float(context[unit_key])
            except (TypeError, ValueError):
                return 0.0

        if "detected_amount" in context:
            try:
                return float(context["detected_amount"])
            except (TypeError, ValueError):
                return 0.0

        return 0.0


class FrequencyChecker(QuestCompletionChecker):
    """
    Evaluates frequency-based quest completion.

    Tracks how many times an action occurs within a defined period
    (day, week, month). Occurrences are stored in user_quest.quest_metadata.

    Quest template condition:
        {"type": "frequency", "target": 3, "period": "week"}

    Metadata structure:
        {"occurrences": [{"entry_id": "uuid", "date": "YYYY-MM-DD"}]}
    """

    def check_completion(
        self,
        db: "Session",
        user_quest: "UserMissionQuest",
        context: dict,
    ) -> tuple[bool, int]:
        condition = self._get_completion_condition(user_quest)
        target = int(condition.get("target", 1))
        period = condition.get("period", "week")

        start, end = self._get_current_period_bounds(period)

        occurrences = list(user_quest.quest_metadata.get("occurrences", []))
        occurrences = self._filter_occurrences_by_period(occurrences, start, end)

        entry_id = context.get("journal_entry_id") or context.get("entry_id")
        entry_date = self._extract_entry_date(db, user_quest, context, entry_id)

        if entry_id and entry_date and self._in_period(entry_date, start, end):
            if not any(occ.get("entry_id") == entry_id for occ in occurrences):
                occurrences.append(
                    {
                        "entry_id": entry_id,
                        "date": entry_date.date().isoformat(),
                    }
                )

        user_quest.quest_metadata["occurrences"] = occurrences

        if target <= 0:
            return (True, 100)

        count = len(occurrences)
        progress = min(100, int((count / target) * 100))
        is_complete = count >= target

        return (is_complete, progress)

    def _get_completion_condition(self, user_quest: "UserMissionQuest") -> dict:
        if user_quest.template and user_quest.template.completion_condition:
            return user_quest.template.completion_condition
        return {}

    def _get_current_period_bounds(self, period: str) -> tuple[datetime, datetime]:
        now = datetime.utcnow()
        day_start = datetime(now.year, now.month, now.day)

        if period == "day":
            start = day_start
            end = start + timedelta(days=1)
            return start, end

        if period == "month":
            start = datetime(now.year, now.month, 1)
            if now.month == 12:
                end = datetime(now.year + 1, 1, 1)
            else:
                end = datetime(now.year, now.month + 1, 1)
            return start, end

        week_start = day_start - timedelta(days=day_start.weekday())
        week_end = week_start + timedelta(days=7)
        return week_start, week_end

    def _filter_occurrences_by_period(
        self,
        occurrences: list[dict],
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        filtered: list[dict] = []
        for occurrence in occurrences:
            date_value = occurrence.get("date")
            if not date_value:
                continue
            try:
                occurrence_date = datetime.fromisoformat(str(date_value))
            except ValueError:
                continue
            if self._in_period(occurrence_date, start, end):
                filtered.append(occurrence)
        return filtered

    def _extract_entry_date(
        self,
        db: "Session",
        user_quest: "UserMissionQuest",
        context: dict,
        entry_id: str | None,
    ) -> datetime | None:
        for key in ("journal_date", "journal_created_at", "entry_date", "created_at"):
            if key in context:
                value = context[key]
                if isinstance(value, datetime):
                    return value
                try:
                    return datetime.fromisoformat(str(value))
                except ValueError:
                    return None

        if entry_id and db is not None:
            entry = (
                db.query(JournalEntry)
                .filter(
                    JournalEntry.id == entry_id,
                    JournalEntry.user_id == user_quest.user_id,
                )
                .one_or_none()
            )
            if entry and entry.created_at:
                return entry.created_at

        return None

    def _in_period(self, value: datetime, start: datetime, end: datetime) -> bool:
        return start <= value < end
