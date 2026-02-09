"""Tests for quest completion checker base classes."""

import pytest

from app.core.quests.base import CompletionType, QuestCompletionChecker


class DummyChecker(QuestCompletionChecker):
    def check_completion(self, db, user_quest, context):
        return True, 1


class ParentChecker(QuestCompletionChecker):
    def check_completion(self, db, user_quest, context):
        return super().check_completion(db, user_quest, context)


def test_quest_completion_checker_is_abstract() -> None:
    with pytest.raises(TypeError):
        QuestCompletionChecker()


def test_completion_type_enum_values() -> None:
    assert CompletionType.YES_NO.value == "yes_no"
    assert CompletionType.ACCUMULATION.value == "accumulation"
    assert CompletionType.FREQUENCY.value == "frequency"
    assert CompletionType.KEYWORD_MATCH.value == "keyword_match"


def test_completion_type_enum_members_exact() -> None:
    assert {member.value for member in CompletionType} == {
        "yes_no",
        "accumulation",
        "frequency",
        "keyword_match",
    }


def test_check_completion_returns_tuple() -> None:
    checker = DummyChecker()
    result = checker.check_completion(None, None, {})

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)
    assert isinstance(result[1], int)


def test_check_completion_super_raises_not_implemented() -> None:
    checker = ParentChecker()
    with pytest.raises(NotImplementedError):
        checker.check_completion(None, None, {})


def test_check_completion_receives_context_unchanged() -> None:
    sentinel = object()

    class ContextChecker(QuestCompletionChecker):
        def check_completion(self, db, user_quest, context):
            assert context is sentinel
            return False, 0

    checker = ContextChecker()
    result = checker.check_completion(None, None, sentinel)

    assert result == (False, 0)


def test_check_completion_allows_zero_progress() -> None:
    class ZeroProgressChecker(QuestCompletionChecker):
        def check_completion(self, db, user_quest, context):
            return False, 0

    checker = ZeroProgressChecker()
    result = checker.check_completion(None, None, {})

    assert result == (False, 0)


def test_check_completion_negative_progress_is_int() -> None:
    class NegativeProgressChecker(QuestCompletionChecker):
        def check_completion(self, db, user_quest, context):
            return False, -5

    checker = NegativeProgressChecker()
    result = checker.check_completion(None, None, {})

    assert isinstance(result[1], int)


def test_abstract_subclass_without_check_completion_fails() -> None:
    class InvalidChecker(QuestCompletionChecker):
        pass

    with pytest.raises(TypeError):
        InvalidChecker()
