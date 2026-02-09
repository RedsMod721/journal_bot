"""
Tests for compound title unlock conditions.
"""
from datetime import datetime, timedelta

from app.core.titles.conditions import CompoundCondition
from app.models.journal_entry import JournalEntry
from app.models.mission_quest import UserMissionQuest
from app.models.theme import Theme


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


class TestCompoundConditions:
    def test_and_condition_both_true(self, db_session, sample_user, sample_theme, sample_skill) -> None:
        evaluator = CompoundCondition()
        sample_theme.level = 10
        sample_skill.rank = "Expert"
        db_session.commit()

        condition = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                {"type": "skill_rank", "rank": "Expert"},
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_and_condition_one_false(self, db_session, sample_user, sample_theme, sample_skill) -> None:
        evaluator = CompoundCondition()
        sample_theme.level = 10
        sample_skill.rank = "Beginner"
        db_session.commit()

        condition = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                {"type": "skill_rank", "rank": "Expert"},
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_or_condition_one_true(self, db_session, sample_user, sample_theme) -> None:
        evaluator = CompoundCondition()
        sample_theme.xp = 100.0
        db_session.commit()

        start = datetime(2025, 1, 1)
        _create_journal_entry(db_session, sample_user.id, start)
        _create_journal_entry(db_session, sample_user.id, start + timedelta(days=1))

        condition = {
            "type": "or",
            "conditions": [
                {"type": "journal_streak", "value": 2},
                {"type": "total_xp", "value": 1000},
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_or_condition_both_false(self, db_session, sample_user, sample_theme) -> None:
        evaluator = CompoundCondition()
        sample_theme.xp = 0.0
        db_session.commit()

        condition = {
            "type": "or",
            "conditions": [
                {"type": "journal_streak", "value": 2},
                {"type": "total_xp", "value": 1000},
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_not_condition_negates_result(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        quest = _create_quest(db_session, sample_user.id, status="failed")

        condition = {
            "type": "not",
            "condition": {"type": "quest_failed", "quest_id": quest.id},
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_nested_and_or_conditions(self, db_session, sample_user, sample_theme, sample_skill) -> None:
        evaluator = CompoundCondition()
        sample_theme.level = 10
        sample_theme.xp = 100.0
        sample_skill.rank = "Expert"
        db_session.commit()

        condition = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                {
                    "type": "or",
                    "conditions": [
                        {"type": "skill_rank", "rank": "Expert"},
                        {"type": "total_xp", "value": 5000},
                    ],
                },
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_deeply_nested_conditions(self, db_session, sample_user, sample_theme, sample_skill) -> None:
        evaluator = CompoundCondition()
        sample_theme.level = 0
        sample_theme.xp = 0.0
        sample_skill.rank = "Beginner"
        db_session.commit()

        quest = _create_quest(db_session, sample_user.id, status="completed")

        condition = {
            "type": "and",
            "conditions": [
                {
                    "type": "or",
                    "conditions": [
                        {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                        {"type": "not", "condition": {"type": "quest_failed", "quest_id": quest.id}},
                    ],
                },
                {
                    "type": "not",
                    "condition": {
                        "type": "or",
                        "conditions": [
                            {"type": "skill_rank", "rank": "Expert"},
                            {"type": "total_xp", "value": 5000},
                        ],
                    },
                },
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_compound_with_all_three_operators(self, db_session, sample_user, sample_theme, sample_skill) -> None:
        evaluator = CompoundCondition()
        sample_theme.level = 10
        sample_skill.rank = "Expert"
        db_session.commit()

        start = datetime(2025, 2, 1)
        _create_journal_entry(db_session, sample_user.id, start)
        _create_journal_entry(db_session, sample_user.id, start + timedelta(days=1))

        condition = {
            "type": "or",
            "conditions": [
                {
                    "type": "and",
                    "conditions": [
                        {"type": "theme_level", "theme": sample_theme.name, "value": 10},
                        {"type": "skill_rank", "rank": "Expert"},
                    ],
                },
                {"type": "not", "condition": {"type": "journal_streak", "value": 2}},
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True
