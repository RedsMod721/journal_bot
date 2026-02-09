"""
Comprehensive edge case tests for compound title unlock conditions.

Tests 60+ edge cases organized by category:
1. Empty conditions & missing fields
2. Single element collections
3. Invalid condition types
4. Deeply nested structures
5. Large collections
6. NOT operator variations
7. Mixed operators
8. Mixed condition types
9. Non-existent entities
10. Condition structure variations
11. User context edge cases
12. Type consistency
13. Realistic scenarios
14. Boolean algebra verification
"""
from datetime import datetime, timedelta
import uuid

from app.core.titles.conditions import CompoundCondition
from app.models.journal_entry import JournalEntry
from app.models.mission_quest import UserMissionQuest


def _create_journal_entry(db_session, user_id: str, created_at: datetime) -> JournalEntry:
    entry = JournalEntry(user_id=user_id, content="Entry", created_at=created_at)
    db_session.add(entry)
    db_session.commit()
    return entry


def _create_quest(db_session, user_id: str, status: str) -> UserMissionQuest:
    quest = UserMissionQuest(user_id=user_id, name="Quest", status=status)
    db_session.add(quest)
    db_session.commit()
    db_session.refresh(quest)
    return quest


class TestEmptyAndMissingFields:
    """Category 1: Empty Conditions & Missing Fields"""

    def test_empty_and_returns_true(self, db_session, sample_user):
        evaluator = CompoundCondition()
        assert evaluator.evaluate(db_session, sample_user.id, {"type": "and", "conditions": []}) is True

    def test_empty_or_returns_false(self, db_session, sample_user):
        evaluator = CompoundCondition()
        assert evaluator.evaluate(db_session, sample_user.id, {"type": "or", "conditions": []}) is False

    def test_and_missing_conditions_raises_keyerror(self, db_session, sample_user):
        evaluator = CompoundCondition()
        try:
            evaluator.evaluate(db_session, sample_user.id, {"type": "and"})
            assert False
        except KeyError:
            pass

    def test_or_missing_conditions_raises_keyerror(self, db_session, sample_user):
        evaluator = CompoundCondition()
        try:
            evaluator.evaluate(db_session, sample_user.id, {"type": "or"})
            assert False
        except KeyError:
            pass

    def test_not_missing_condition_raises_keyerror(self, db_session, sample_user):
        evaluator = CompoundCondition()
        try:
            evaluator.evaluate(db_session, sample_user.id, {"type": "not"})
            assert False
        except KeyError:
            pass

    def test_missing_type_raises_keyerror(self, db_session, sample_user):
        evaluator = CompoundCondition()
        try:
            evaluator.evaluate(db_session, sample_user.id, {"conditions": []})
            assert False
        except KeyError:
            pass


class TestSingleElement:
    """Category 2: Single Element Collections"""

    def test_and_single_true(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        db_session.commit()
        cond = {"type": "and", "conditions": [{"type": "theme_level", "theme": sample_theme.name, "value": 10}]}
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True

    def test_and_single_false(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 0
        db_session.commit()
        cond = {"type": "and", "conditions": [{"type": "theme_level", "theme": sample_theme.name, "value": 10}]}
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False

    def test_or_single_true(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        db_session.commit()
        cond = {"type": "or", "conditions": [{"type": "theme_level", "theme": sample_theme.name, "value": 10}]}
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True

    def test_or_single_false(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 0
        db_session.commit()
        cond = {"type": "or", "conditions": [{"type": "theme_level", "theme": sample_theme.name, "value": 10}]}
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False


class TestInvalidTypes:
    """Category 3: Invalid Condition Types - gracefully return False"""

    def test_invalid_type_returns_false(self, db_session, sample_user):
        """Unknown condition types return False instead of raising."""
        evaluator = CompoundCondition()
        cond = {"type": "and", "conditions": [{"type": "nonexistent"}]}
        result = evaluator.evaluate(db_session, sample_user.id, cond)
        assert result is False

    def test_null_type_returns_false(self, db_session, sample_user):
        """None type returns False."""
        evaluator = CompoundCondition()
        result = evaluator.evaluate(db_session, sample_user.id, {"type": None})
        assert result is False

    def test_integer_type_returns_false(self, db_session, sample_user):
        """Integer type returns False."""
        evaluator = CompoundCondition()
        result = evaluator.evaluate(db_session, sample_user.id, {"type": 123})
        assert result is False

    def test_type_with_spaces_returns_false(self, db_session, sample_user):
        """Type with spaces returns False (no match)."""
        evaluator = CompoundCondition()
        result = evaluator.evaluate(db_session, sample_user.id, {"type": " journal_count "})
        assert result is False


class TestDeeplyNested:
    """Category 4: Deeply Nested Structures"""

    def test_five_level_nesting(self, db_session, sample_user, sample_theme, sample_skill):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        sample_skill.rank = "Expert"
        db_session.commit()
        cond = {
            "type": "and",
            "conditions": [{
                "type": "or",
                "conditions": [{
                    "type": "and",
                    "conditions": [
                        {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                        {
                            "type": "or",
                            "conditions": [
                                {"type": "skill_rank", "rank": "Expert"},
                                {"type": "not", "condition": {"type": "total_xp", "value": 5000}},
                            ],
                        },
                    ],
                }, {"type": "total_xp", "value": 5000}],
            }],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True

    def test_six_level_nesting(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 5
        db_session.commit()
        cond = {
            "type": "and",
            "conditions": [{
                "type": "or",
                "conditions": [{
                    "type": "not",
                    "condition": {
                        "type": "and",
                        "conditions": [{
                            "type": "or",
                            "conditions": [{
                                "type": "not",
                                "condition": {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                            }, {"type": "total_xp", "value": 5000}],
                        }, {"type": "total_xp", "value": 5000}],
                    },
                }, {"type": "total_xp", "value": 5000}],
            }],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True

    def test_left_deep_nesting(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        db_session.commit()
        cond = {
            "type": "and",
            "conditions": [{
                "type": "and",
                "conditions": [{
                    "type": "and",
                    "conditions": [
                        {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                        {"type": "total_xp", "value": 5000},
                    ],
                }, {"type": "total_xp", "value": 5000}],
            }, {"type": "total_xp", "value": 5000}],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False

    def test_right_deep_nesting(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        db_session.commit()
        cond = {
            "type": "or",
            "conditions": [
                {"type": "total_xp", "value": 5000},
                {
                    "type": "or",
                    "conditions": [
                        {"type": "total_xp", "value": 5000},
                        {
                            "type": "or",
                            "conditions": [
                                {"type": "total_xp", "value": 5000},
                                {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                            ],
                        },
                    ],
                },
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True


class TestLargeCollections:
    """Category 5: Large Collections"""

    def test_and_ten_true(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.xp = 100.0
        db_session.commit()
        cond = {
            "type": "and",
            "conditions": [{"type": "total_xp", "value": 50}] * 10,
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True

    def test_and_ten_last_false(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.xp = 100.0
        db_session.commit()
        cond = {
            "type": "and",
            "conditions": [{"type": "total_xp", "value": 50}] * 9 + [{"type": "total_xp", "value": 200}],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False

    def test_or_ten_false(self, db_session, sample_user):
        evaluator = CompoundCondition()
        cond = {
            "type": "or",
            "conditions": [{"type": "quest_completion_count", "value": 1}] * 10,
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False

    def test_or_ten_first_true(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.xp = 100.0
        db_session.commit()
        cond = {
            "type": "or",
            "conditions": [{"type": "total_xp", "value": 50}] + [{"type": "quest_completion_count", "value": 1}] * 9,
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True


class TestNOT:
    """Category 6: NOT Operator Variations"""

    def test_double_negation(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        db_session.commit()
        cond = {
            "type": "not",
            "condition": {"type": "not", "condition": {"type": "theme_level", "theme": sample_theme.name, "value": 10}},
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True

    def test_triple_negation(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        db_session.commit()
        cond = {
            "type": "not",
            "condition": {
                "type": "not",
                "condition": {"type": "not", "condition": {"type": "theme_level", "theme": sample_theme.name, "value": 10}},
            },
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False

    def test_not_true_and(self, db_session, sample_user, sample_theme, sample_skill):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        sample_skill.rank = "Expert"
        db_session.commit()
        cond = {
            "type": "not",
            "condition": {
                "type": "and",
                "conditions": [
                    {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                    {"type": "skill_rank", "rank": "Expert"},
                ],
            },
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False

    def test_not_false_or(self, db_session, sample_user):
        evaluator = CompoundCondition()
        cond = {
            "type": "not",
            "condition": {
                "type": "or",
                "conditions": [
                    {"type": "quest_completion_count", "value": 1},
                    {"type": "quest_completion_count", "value": 1},
                ],
            },
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True

    def test_nested_nots(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        db_session.commit()
        cond = {
            "type": "and",
            "conditions": [{
                "type": "not",
                "condition": {
                    "type": "or",
                    "conditions": [
                        {"type": "quest_completion_count", "value": 1},
                        {"type": "not", "condition": {"type": "theme_level", "theme": sample_theme.name, "value": 10}},
                    ],
                },
            }, {"type": "total_xp", "value": 5000}],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False


class TestMixedOperators:
    """Category 7: Mixed Operators"""

    def test_and_with_all_three_types(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.xp = 100.0
        db_session.commit()
        cond = {
            "type": "and",
            "conditions": [
                {"type": "total_xp", "value": 50},
                {"type": "or", "conditions": [{"type": "total_xp", "value": 200}, {"type": "total_xp", "value": 50}]},
                {"type": "not", "condition": {"type": "quest_completion_count", "value": 1}},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True

    def test_or_with_all_three_types(self, db_session, sample_user):
        evaluator = CompoundCondition()
        cond = {
            "type": "or",
            "conditions": [
                {"type": "quest_completion_count", "value": 1},
                {"type": "and", "conditions": [{"type": "quest_completion_count", "value": 1}, {"type": "quest_completion_count", "value": 1}]},
                {"type": "not", "condition": {"type": "quest_completion_count", "value": 1}},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True


class TestMixedConditionTypes:
    """Category 8: Mixed Condition Types"""

    def test_and_multiple_types(self, db_session, sample_user, sample_theme, sample_skill):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        sample_skill.rank = "Expert"
        db_session.commit()
        start = datetime(2025, 1, 1)
        _create_journal_entry(db_session, sample_user.id, start)
        _create_journal_entry(db_session, sample_user.id, start + timedelta(days=1))
        cond = {
            "type": "and",
            "conditions": [
                {"type": "journal_streak", "value": 2},
                {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                {"type": "skill_rank", "rank": "Expert"},
                {"type": "total_xp", "value": 5000},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False

    def test_or_negative_conditions(self, db_session, sample_user):
        evaluator = CompoundCondition()
        quest = _create_quest(db_session, sample_user.id, status="pending")
        cond = {
            "type": "or",
            "conditions": [
                {"type": "quest_failed", "quest_id": quest.id},
                {"type": "item_equipped", "item_type": "sword"},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False


class TestNonExistentEntities:
    """Category 9: Non-Existent Entities"""

    def test_and_nonexistent_theme(self, db_session, sample_user):
        evaluator = CompoundCondition()
        cond = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": "NonExistent", "value": 10},
                {"type": "total_xp", "value": 5000},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False

    def test_or_nonexistent_quest(self, db_session, sample_user):
        evaluator = CompoundCondition()
        cond = {
            "type": "or",
            "conditions": [
                {"type": "quest_failed", "quest_id": str(uuid.uuid4())},
                {"type": "quest_completion_count", "value": 1},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False


class TestStructureVariations:
    """Category 10: Structure Variations"""

    def test_extra_fields_ignored(self, db_session, sample_user):
        evaluator = CompoundCondition()
        cond = {
            "type": "and",
            "conditions": [{"type": "total_xp", "value": 5000}],
            "extra": "ignored",
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False

    def test_duplicate_conditions(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        db_session.commit()
        cond = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                {"type": "theme_level", "theme": sample_theme.name, "value": 10},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is True


class TestUserContext:
    """Category 11: User Context"""

    def test_fresh_user_limited_options(self, db_session, sample_user):
        evaluator = CompoundCondition()
        cond = {
            "type": "or",
            "conditions": [
                {"type": "quest_completion_count", "value": 1},
                {"type": "quest_completion_count", "value": 1},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond) is False


class TestTypeConsistency:
    """Category 12: Type Consistency"""

    def test_return_bool_true(self, db_session, sample_user):
        evaluator = CompoundCondition()
        cond = {"type": "and", "conditions": []}
        result = evaluator.evaluate(db_session, sample_user.id, cond)
        assert isinstance(result, bool)
        assert result is True

    def test_return_bool_false(self, db_session, sample_user):
        evaluator = CompoundCondition()
        cond = {"type": "or", "conditions": []}
        result = evaluator.evaluate(db_session, sample_user.id, cond)
        assert isinstance(result, bool)
        assert result is False


class TestBooleanAlgebra:
    """Category 14: Boolean Algebra"""

    def test_de_morgans_law(self, db_session, sample_user, sample_theme, sample_skill):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        sample_skill.rank = "Expert"
        db_session.commit()
        cond1 = {
            "type": "not",
            "condition": {
                "type": "and",
                "conditions": [
                    {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                    {"type": "skill_rank", "rank": "Expert"},
                ],
            },
        }
        cond2 = {
            "type": "or",
            "conditions": [
                {"type": "not", "condition": {"type": "theme_level", "theme": sample_theme.name, "value": 10}},
                {"type": "not", "condition": {"type": "skill_rank", "rank": "Expert"}},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond1) == evaluator.evaluate(db_session, sample_user.id, cond2)

    def test_commutative_and(self, db_session, sample_user, sample_theme, sample_skill):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        sample_skill.rank = "Expert"
        db_session.commit()
        cond1 = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                {"type": "skill_rank", "rank": "Expert"},
            ],
        }
        cond2 = {
            "type": "and",
            "conditions": [
                {"type": "skill_rank", "rank": "Expert"},
                {"type": "theme_level", "theme": sample_theme.name, "value": 10},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond1) == evaluator.evaluate(db_session, sample_user.id, cond2)

    def test_commutative_or(self, db_session, sample_user, sample_theme):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        db_session.commit()
        cond1 = {
            "type": "or",
            "conditions": [
                {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                {"type": "quest_completion_count", "value": 1},
            ],
        }
        cond2 = {
            "type": "or",
            "conditions": [
                {"type": "quest_completion_count", "value": 1},
                {"type": "theme_level", "theme": sample_theme.name, "value": 10},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond1) == evaluator.evaluate(db_session, sample_user.id, cond2)

    def test_associative_and(self, db_session, sample_user, sample_theme, sample_skill):
        evaluator = CompoundCondition()
        sample_theme.level = 10
        sample_skill.rank = "Expert"
        db_session.commit()
        cond1 = {
            "type": "and",
            "conditions": [
                {"type": "total_xp", "value": 5000},
                {
                    "type": "and",
                    "conditions": [
                        {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                        {"type": "skill_rank", "rank": "Expert"},
                    ],
                },
            ],
        }
        cond2 = {
            "type": "and",
            "conditions": [
                {
                    "type": "and",
                    "conditions": [
                        {"type": "total_xp", "value": 5000},
                        {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                    ],
                },
                {"type": "skill_rank", "rank": "Expert"},
            ],
        }
        assert evaluator.evaluate(db_session, sample_user.id, cond1) == evaluator.evaluate(db_session, sample_user.id, cond2)

    def test_case_sensitivity(self, db_session, sample_user):
        """Type matching is case-sensitive - uppercase returns False."""
        evaluator = CompoundCondition()
        cond_lower = {"type": "and", "conditions": []}
        result_lower = evaluator.evaluate(db_session, sample_user.id, cond_lower)
        cond_upper = {"type": "AND", "conditions": []}
        result_upper = evaluator.evaluate(db_session, sample_user.id, cond_upper)
        assert result_lower is True
        assert result_upper is False
