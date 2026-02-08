"""
Title unlock condition evaluation system.

This package provides the framework for evaluating whether users
have met the unlock conditions for titles/achievements.
"""

from app.core.titles.base import ConditionEvaluator, ConditionType
from app.core.titles.conditions import (
    JournalCountCondition,
    JournalStreakCondition,
    QuestCompletionCountCondition,
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
]
