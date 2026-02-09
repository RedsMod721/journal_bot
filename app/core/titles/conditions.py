"""
Concrete implementations of title unlock condition evaluators.

This module provides evaluators for various unlock condition types:
- Streak-based: Journal streaks, days active
- Level-based: Theme levels, skill levels, skill ranks
- XP-based: Total XP, theme-specific XP
- Quest-based: Completion counts, specific quest completion
- Count-based: Journal entry counts

Each evaluator inherits from ConditionEvaluator and implements
the evaluate() method to check if a user meets the condition.
"""

from datetime import date
from typing import TYPE_CHECKING, Iterable

from sqlalchemy import func

from app.core.titles.base import ConditionEvaluator
from app.models.item import ItemTemplate, UserItem
from app.models.journal_entry import JournalEntry
from app.models.mission_quest import UserMissionQuest
from app.models.skill import Skill
from app.models.theme import Theme

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _require_field(condition: dict, field: str) -> None:
    if field not in condition:
        raise KeyError(f"Missing required field: {field}")


def _get_distinct_entry_dates(entries: Iterable[JournalEntry]) -> list[date]:
    unique_dates = {entry.created_at.date() for entry in entries if entry.created_at}
    return sorted(unique_dates)


def _max_consecutive_streak(dates: list[date]) -> int:
    if not dates:
        return 0

    max_streak = 1
    current_streak = 1

    for index in range(1, len(dates)):
        delta_days = (dates[index] - dates[index - 1]).days
        if delta_days == 1:
            current_streak += 1
        else:
            current_streak = 1
        max_streak = max(max_streak, current_streak)

    return max_streak


# Corrosion levels from best to worst
CORROSION_LEVELS = ["Fresh", "Familiar", "Dusty", "Rusty", "Forgotten"]

# Skill ranks from lowest to highest
SKILL_RANK_ORDER = [
    "Beginner",
    "Amateur",
    "Intermediate",
    "Advanced",
    "Expert",
    "Master",
]


def _get_corrosion_index(level: str) -> int:
    """Get numeric index for corrosion level. Returns -1 if invalid."""
    try:
        return CORROSION_LEVELS.index(level)
    except ValueError:
        return -1


class JournalStreakCondition(ConditionEvaluator):
    """
    Evaluates journal streak conditions.

    Checks if the user has journaled for a consecutive number of days.

    Condition format:
        {"type": "journal_streak", "value": 7}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user has a journal streak of at least the required days.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "value" (required streak length)

        Returns:
            True if user has streaked for at least the required days
        """
        _require_field(condition, "value")

        entries = (
            db.query(JournalEntry)
            .filter(JournalEntry.user_id == user_id)
            .order_by(JournalEntry.created_at.asc())
            .all()
        )

        if not entries:
            return False

        dates = _get_distinct_entry_dates(entries)
        return _max_consecutive_streak(dates) >= condition["value"]


class ThemeLevelCondition(ConditionEvaluator):
    """
    Evaluates theme level conditions.

    Checks if a specific theme has reached a required level.

    Condition format:
        {"type": "theme_level", "theme": "Education", "value": 10}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user's theme has reached the required level.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "theme" (name) and "value" (required level)

        Returns:
            True if theme exists and has reached the required level
        """
        _require_field(condition, "theme")
        _require_field(condition, "value")

        theme_name = condition["theme"]

        theme = (
            db.query(Theme)
            .filter(Theme.user_id == user_id, Theme.name == theme_name)
            .first()
        )

        if not theme:
            return False

        return theme.level >= condition["value"]


class SkillLevelCondition(ConditionEvaluator):
    """
    Evaluates skill level conditions.

    Checks if a specific skill has reached a required level.

    Condition format:
        {"type": "skill_level", "skill": "Python", "value": 15}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user's skill has reached the required level.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "skill" (name) and "value" (required level)

        Returns:
            True if skill exists and has reached the required level
        """
        _require_field(condition, "skill")
        _require_field(condition, "value")

        skill_name = condition["skill"]

        skill = (
            db.query(Skill)
            .filter(Skill.user_id == user_id, Skill.name == skill_name)
            .first()
        )

        if not skill:
            return False

        return skill.level >= condition["value"]


class TotalXPCondition(ConditionEvaluator):
    """
    Evaluates total XP conditions.

    Checks if the sum of XP across all user's themes meets a threshold.

    Condition format:
        {"type": "total_xp", "value": 5000}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user's total XP across all themes meets the threshold.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "value" (required total XP)

        Returns:
            True if total XP meets or exceeds the required value
        """
        _require_field(condition, "value")

        total_xp = (
            db.query(func.coalesce(func.sum(Theme.xp), 0.0))
            .filter(Theme.user_id == user_id)
            .scalar()
        )

        if total_xp == 0.0:
            theme_exists = (
                db.query(Theme.id).filter(Theme.user_id == user_id).first() is not None
            )
            if not theme_exists:
                return False

        return total_xp >= condition["value"]


class ThemeXPCondition(ConditionEvaluator):
    """
    Evaluates theme-specific XP conditions.

    Checks if a specific theme has accumulated enough XP.

    Condition format:
        {"type": "theme_xp", "theme": "Education", "value": 1000}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user's theme has accumulated the required XP.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "theme" (name) and "value" (required XP)

        Returns:
            True if theme exists and has enough XP
        """
        _require_field(condition, "theme")
        _require_field(condition, "value")

        theme_name = condition["theme"]

        theme = (
            db.query(Theme)
            .filter(Theme.user_id == user_id, Theme.name == theme_name)
            .first()
        )

        if not theme:
            return False

        return theme.xp >= condition["value"]


class QuestCompletionCountCondition(ConditionEvaluator):
    """
    Evaluates quest completion count conditions.

    Checks if the user has completed a certain number of quests.

    Condition format:
        {"type": "quest_completion_count", "value": 10}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user has completed the required number of quests.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "value" (required completion count)

        Returns:
            True if user has completed at least the required number of quests
        """
        _require_field(condition, "value")

        completed_count = (
            db.query(UserMissionQuest)
            .filter(
                UserMissionQuest.user_id == user_id,
                UserMissionQuest.status == "completed",
            )
            .count()
        )

        if completed_count == 0:
            quest_exists = (
                db.query(UserMissionQuest.id)
                .filter(UserMissionQuest.user_id == user_id)
                .first()
                is not None
            )
            if not quest_exists:
                return False

        return completed_count >= condition["value"]


class SpecificQuestCompletedCondition(ConditionEvaluator):
    """
    Evaluates specific quest completion conditions.

    Checks if a specific quest has been completed by the user.

    Condition format:
        {"type": "specific_quest_completed", "quest_id": "quest-uuid"}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user has completed a specific quest.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "quest_id" (the quest's UUID)

        Returns:
            True if the specific quest is completed
        """
        _require_field(condition, "quest_id")

        quest = (
            db.query(UserMissionQuest)
            .filter(
                UserMissionQuest.id == condition["quest_id"],
                UserMissionQuest.user_id == user_id,
            )
            .one_or_none()
        )

        if quest is None:
            return False

        return quest.status == "completed"


class SkillRankCondition(ConditionEvaluator):
    """
    Evaluates skill rank conditions.

    Checks if any of the user's skills has reached a specific rank.

    Condition format:
        {"type": "skill_rank", "rank": "Expert"}

    Valid ranks: Beginner, Amateur, Intermediate, Advanced, Expert, Master
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user has any skill at the required rank or higher.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "rank" (required skill rank)

        Returns:
            True if any skill has reached at least the required rank
        """
        _require_field(condition, "rank")

        required_rank = condition["rank"]
        if required_rank not in SKILL_RANK_ORDER:
            return False

        required_index = SKILL_RANK_ORDER.index(required_rank)
        acceptable_ranks = SKILL_RANK_ORDER[required_index:]

        return (
            db.query(Skill)
            .filter(Skill.user_id == user_id, Skill.rank.in_(acceptable_ranks))
            .first()
            is not None
        )


class JournalCountCondition(ConditionEvaluator):
    """
    Evaluates journal entry count conditions.

    Checks if the user has created a certain number of journal entries.

    Condition format:
        {"type": "journal_count", "value": 100}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user has created the required number of journal entries.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "value" (required entry count)

        Returns:
            True if user has at least the required number of entries
        """
        _require_field(condition, "value")

        entry_count = (
            db.query(JournalEntry)
            .filter(JournalEntry.user_id == user_id)
            .count()
        )

        if entry_count == 0:
            return False

        return entry_count >= condition["value"]


class TimeBasedCondition(ConditionEvaluator):
    """
    Evaluates time-based activity conditions.

    Checks if the user has been active (has journal entries) on a
    certain number of unique days (not necessarily consecutive).

    Condition format:
        {"type": "time_based", "days_active": 30}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user has been active for the required number of days.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "days_active" (required unique days)

        Returns:
            True if user has entries on at least the required number of days
        """
        _require_field(condition, "days_active")

        entries = db.query(JournalEntry).filter(JournalEntry.user_id == user_id).all()
        if not entries:
            return False

        unique_days = _get_distinct_entry_dates(entries)

        return len(unique_days) >= condition["days_active"]


# =============================================================================
# NEGATIVE CONDITION EVALUATORS
# =============================================================================


class CorrosionLevelCondition(ConditionEvaluator):
    """
    Evaluates theme corrosion level conditions.

    Checks if a theme's corrosion has reached or exceeded a minimum level.
    Used for negative titles that reflect neglect.

    Corrosion levels (from best to worst):
        Fresh → Familiar → Dusty → Rusty → Forgotten

    Condition format:
        {"type": "corrosion_level", "theme": "Education", "min_level": "Rusty"}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user's theme has reached the minimum corrosion level.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "theme" (name) and "min_level" (corrosion level)

        Returns:
            True if theme exists and corrosion >= min_level
        """
        _require_field(condition, "theme")
        _require_field(condition, "min_level")

        min_level = condition["min_level"]
        min_index = _get_corrosion_index(min_level)

        if min_index == -1:
            return False

        theme = (
            db.query(Theme)
            .filter(Theme.user_id == user_id, Theme.name == condition["theme"])
            .first()
        )

        if not theme:
            return False

        current_index = _get_corrosion_index(theme.corrosion_level)

        if current_index == -1:
            return False

        return current_index >= min_index


class QuestFailedCondition(ConditionEvaluator):
    """
    Evaluates quest failure conditions.

    Checks if a specific quest has been failed by the user.
    Used for negative titles that reflect setbacks.

    Condition format:
        {"type": "quest_failed", "quest_id": "quest-uuid"}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user has failed a specific quest.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "quest_id" (the quest's UUID)

        Returns:
            True if the specific quest has status="failed"
        """
        _require_field(condition, "quest_id")

        quest = (
            db.query(UserMissionQuest)
            .filter(
                UserMissionQuest.id == condition["quest_id"],
                UserMissionQuest.user_id == user_id,
            )
            .one_or_none()
        )

        if quest is None:
            return False

        return quest.status == "failed"


class ItemEquippedCondition(ConditionEvaluator):
    """
    Evaluates item equipped conditions.

    Checks if the user has any equipped item of a specific type.
    Can be used for both positive and negative titles.

    Condition format:
        {"type": "item_equipped", "item_type": "cursed_item"}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        """
        Check if user has any equipped item of the specified type.

        Args:
            db: Database session
            user_id: User's UUID
            condition: Must contain "item_type" (the item type to check)

        Returns:
            True if user has at least one equipped item of the specified type
        """
        _require_field(condition, "item_type")

        equipped_item = (
            db.query(UserItem)
            .join(ItemTemplate, UserItem.template_id == ItemTemplate.id)
            .filter(
                UserItem.user_id == user_id,
                UserItem.is_equipped == True,  # noqa: E712
                ItemTemplate.item_type == condition["item_type"],
            )
            .first()
        )

        return equipped_item is not None


class CompoundCondition(ConditionEvaluator):
    """
    Evaluates compound boolean conditions.

    Supports AND, OR, and NOT logic with recursive evaluation.

    Condition formats:
        AND: {"type": "and", "conditions": [ ... ]}
        OR: {"type": "or", "conditions": [ ... ]}
        NOT: {"type": "not", "condition": { ... }}
    """

    def evaluate(self, db: "Session", user_id: str, condition: dict) -> bool:
        _require_field(condition, "type")

        condition_type = condition["type"]

        if condition_type == "and":
            _require_field(condition, "conditions")
            return all(
                self._evaluate_condition(db, user_id, sub_condition)
                for sub_condition in condition["conditions"]
            )

        if condition_type == "or":
            _require_field(condition, "conditions")
            return any(
                self._evaluate_condition(db, user_id, sub_condition)
                for sub_condition in condition["conditions"]
            )

        if condition_type == "not":
            _require_field(condition, "condition")
            return not self._evaluate_condition(db, user_id, condition["condition"])

        evaluator = self._get_evaluator(condition_type)
        if evaluator is None:
            return False

        return evaluator.evaluate(db, user_id, condition)

    def _evaluate_condition(self, db: "Session", user_id: str, condition: dict) -> bool:
        _require_field(condition, "type")
        condition_type = condition["type"]

        if condition_type in {"and", "or", "not"}:
            return self.evaluate(db, user_id, condition)

        evaluator = self._get_evaluator(condition_type)
        if evaluator is None:
            return False

        return evaluator.evaluate(db, user_id, condition)

    def _get_evaluator(self, condition_type: str) -> ConditionEvaluator | None:
        evaluators: dict[str, ConditionEvaluator] = {
            "journal_streak": JournalStreakCondition(),
            "theme_level": ThemeLevelCondition(),
            "skill_level": SkillLevelCondition(),
            "total_xp": TotalXPCondition(),
            "theme_xp": ThemeXPCondition(),
            "quest_completion_count": QuestCompletionCountCondition(),
            "specific_quest_completed": SpecificQuestCompletedCondition(),
            "skill_rank": SkillRankCondition(),
            "journal_count": JournalCountCondition(),
            "time_based": TimeBasedCondition(),
            "corrosion_level": CorrosionLevelCondition(),
            "quest_failed": QuestFailedCondition(),
            "item_equipped": ItemEquippedCondition(),
        }

        return evaluators.get(condition_type)


CONDITION_EVALUATORS: dict[str, ConditionEvaluator] = {
    "journal_streak": JournalStreakCondition(),
    "theme_level": ThemeLevelCondition(),
    "skill_level": SkillLevelCondition(),
    "total_xp": TotalXPCondition(),
    "theme_xp": ThemeXPCondition(),
    "quest_completion_count": QuestCompletionCountCondition(),
    "specific_quest_completed": SpecificQuestCompletedCondition(),
    "skill_rank": SkillRankCondition(),
    "journal_count": JournalCountCondition(),
    "time_based": TimeBasedCondition(),
    "corrosion_level": CorrosionLevelCondition(),
    "quest_failed": QuestFailedCondition(),
    "item_equipped": ItemEquippedCondition(),
    "compound": CompoundCondition(),
    "and": CompoundCondition(),
    "or": CompoundCondition(),
    "not": CompoundCondition(),
}
