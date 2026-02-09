"""
Tests for title unlock condition base interfaces.
"""
import pytest

from app.core.titles.base import ConditionEvaluator, ConditionType


class DummyEvaluator(ConditionEvaluator):
    def evaluate(self, db, user_id, condition):
        return True


class TestConditionEvaluatorBase:
    def test_condition_evaluator_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            ConditionEvaluator()

    def test_condition_evaluator_subclass_implements(self) -> None:
        evaluator = DummyEvaluator()
        assert evaluator.evaluate(None, "user-1", {"type": "theme_level"}) is True


class TestConditionTypeEnum:
    def test_condition_type_enum_has_all_types(self) -> None:
        expected = {
            "journal_streak",
            "journal_count",
            "time_based",
            "theme_level",
            "skill_level",
            "skill_rank",
            "total_xp",
            "theme_xp",
            "quest_completion_count",
            "specific_quest_completed",
            "morning_entries",
            "night_entries",
            "quest_failed",
            "corrosion_level",
            "item_equipped",
            "and",
            "or",
            "not",
        }

        actual = {member.value for member in ConditionType}

        assert actual == expected

    def test_condition_type_enum_values_unique(self) -> None:
        values = [member.value for member in ConditionType]
        assert len(values) == len(set(values))

    def test_condition_type_enum_case_sensitive(self) -> None:
        assert "THEME_LEVEL" not in {member.value for member in ConditionType}

    def test_condition_type_enum_contains_expected_member(self) -> None:
        assert ConditionType.THEME_LEVEL.value == "theme_level"
        assert ConditionType.JOURNAL_STREAK.value == "journal_streak"

    def test_condition_type_enum_iterable_length(self) -> None:
        assert len(list(ConditionType)) == 18
