"""
Title unlock condition evaluation system.

This package provides the framework for evaluating whether users
have met the unlock conditions for titles/achievements.
"""

from app.core.titles.base import ConditionEvaluator, ConditionType
from app.core.titles.conditions import (
    CorrosionLevelCondition,
    ItemEquippedCondition,
    JournalCountCondition,
    JournalStreakCondition,
    QuestCompletionCountCondition,
    QuestFailedCondition,
    SkillLevelCondition,
    SkillRankCondition,
    SpecificQuestCompletedCondition,
    ThemeLevelCondition,
    ThemeXPCondition,
    TimeBasedCondition,
    TotalXPCondition,
)

__all__ = [
    "ConditionEvaluator",
    "ConditionType",
    # Positive conditions
    "JournalCountCondition",
    "JournalStreakCondition",
    "QuestCompletionCountCondition",
    "SkillLevelCondition",
    "SkillRankCondition",
    "SpecificQuestCompletedCondition",
    "ThemeLevelCondition",
    "ThemeXPCondition",
    "TimeBasedCondition",
    "TotalXPCondition",
    # Negative conditions
    "CorrosionLevelCondition",
    "ItemEquippedCondition",
    "QuestFailedCondition",
]
