"""Tests for quest completion checker base classes."""

import pytest

from app.core.quests.base import CompletionType, QuestCompletionChecker


class DummyChecker(QuestCompletionChecker):
    def check_completion(self, db, user_quest, context):
        return True, 1


def test_quest_completion_checker_is_abstract() -> None:
    with pytest.raises(TypeError):
        QuestCompletionChecker()


def test_completion_type_enum_values() -> None:
    assert CompletionType.YES_NO.value == "yes_no"
    assert CompletionType.ACCUMULATION.value == "accumulation"
    assert CompletionType.FREQUENCY.value == "frequency"
    assert CompletionType.KEYWORD_MATCH.value == "keyword_match"


def test_check_completion_returns_tuple() -> None:
    checker = DummyChecker()
    result = checker.check_completion(None, None, {})

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)
    assert isinstance(result[1], int)
