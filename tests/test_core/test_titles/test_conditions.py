"""
Tests for concrete title unlock condition evaluators.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from freezegun import freeze_time

from app.core.titles.conditions import (
    CompoundCondition,
    CorrosionLevelCondition,
    ItemEquippedCondition,
    JournalCountCondition,
    JournalStreakCondition,
    QuestFailedCondition,
    QuestCompletionCountCondition,
    SkillLevelCondition,
    SkillRankCondition,
    SpecificQuestCompletedCondition,
    ThemeLevelCondition,
    ThemeXPCondition,
    TimeBasedCondition,
    TotalXPCondition,
    _max_consecutive_streak,
)
from app.models.journal_entry import JournalEntry
from app.models.item import ItemTemplate, UserItem
from app.models.mission_quest import UserMissionQuest
from app.models.skill import Skill
from app.models.theme import Theme
from app.models.user import User


def _create_user(db_session) -> User:
    user = User(
        username=f"user_{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@example.com",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_journal_entry(db_session, user_id: str, created_at: datetime | None = None) -> JournalEntry:
    entry = JournalEntry(
        user_id=user_id,
        content="Entry",
        created_at=created_at or datetime.utcnow(),
    )
    db_session.add(entry)
    db_session.commit()
    return entry


def _create_quest(db_session, user_id: str, status: str = "completed") -> UserMissionQuest:
    quest = UserMissionQuest(
        user_id=user_id,
        name=f"Quest {uuid4().hex[:6]}",
        status=status,
    )
    db_session.add(quest)
    db_session.commit()
    db_session.refresh(quest)
    return quest


def _create_item_template(db_session, item_type: str) -> ItemTemplate:
    template = ItemTemplate(
        name=f"Item {uuid4().hex[:6]}",
        item_type=item_type,
        rarity="common",
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


def _create_user_item(
    db_session,
    user_id: str,
    template_id: str,
    is_equipped: bool = False,
) -> UserItem:
    user_item = UserItem(
        user_id=user_id,
        template_id=template_id,
        is_equipped=is_equipped,
    )
    db_session.add(user_item)
    db_session.commit()
    db_session.refresh(user_item)
    return user_item


class TestJournalStreakCondition:
    def test_journal_streak_met(self, db_session, sample_user) -> None:
        evaluator = JournalStreakCondition()
        start = datetime(2025, 1, 1)
        for offset in range(7):
            _create_journal_entry(db_session, sample_user.id, start + timedelta(days=offset))

        condition = {"type": "journal_streak", "value": 7}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_journal_streak_not_met(self, db_session, sample_user) -> None:
        evaluator = JournalStreakCondition()
        start = datetime(2025, 1, 1)
        for offset in range(3):
            _create_journal_entry(db_session, sample_user.id, start + timedelta(days=offset))

        condition = {"type": "journal_streak", "value": 7}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_journal_streak_exact_threshold(self, db_session, sample_user) -> None:
        evaluator = JournalStreakCondition()
        start = datetime(2025, 2, 1)
        for offset in range(5):
            _create_journal_entry(db_session, sample_user.id, start + timedelta(days=offset))

        condition = {"type": "journal_streak", "value": 5}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True


class TestConditionHelpers:
    def test_max_consecutive_streak_empty_list(self) -> None:
        assert _max_consecutive_streak([]) == 0

    def test_journal_streak_entity_not_found_returns_false(self, db_session, sample_user) -> None:
        evaluator = JournalStreakCondition()
        condition = {"type": "journal_streak", "value": 1}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_journal_streak_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = JournalStreakCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "journal_streak"})

    def test_journal_streak_edge_case_1(self, db_session, sample_user) -> None:
        evaluator = JournalStreakCondition()
        start = datetime(2025, 3, 1)
        for offset in range(3):
            _create_journal_entry(db_session, sample_user.id, start + timedelta(days=offset))
        _create_journal_entry(db_session, sample_user.id, start + timedelta(days=4))
        _create_journal_entry(db_session, sample_user.id, start + timedelta(days=5))

        condition = {"type": "journal_streak", "value": 4}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_journal_streak_edge_case_2(self, db_session, sample_user) -> None:
        evaluator = JournalStreakCondition()
        same_day = datetime(2025, 4, 1, 10, 0, 0)
        _create_journal_entry(db_session, sample_user.id, same_day)
        _create_journal_entry(db_session, sample_user.id, same_day + timedelta(hours=2))
        _create_journal_entry(db_session, sample_user.id, same_day + timedelta(days=1))

        condition = {"type": "journal_streak", "value": 2}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_journal_streak_with_multiple_users(self, db_session, sample_user) -> None:
        evaluator = JournalStreakCondition()
        other_user = _create_user(db_session)
        start = datetime(2025, 5, 1)
        for offset in range(4):
            _create_journal_entry(db_session, other_user.id, start + timedelta(days=offset))

        condition = {"type": "journal_streak", "value": 3}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False


class TestThemeLevelCondition:
    def test_theme_level_met(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeLevelCondition()
        sample_theme.level = 10
        db_session.commit()

        condition = {"type": "theme_level", "theme": sample_theme.name, "value": 5}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_theme_level_not_met(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeLevelCondition()
        sample_theme.level = 2
        db_session.commit()

        condition = {"type": "theme_level", "theme": sample_theme.name, "value": 5}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_theme_level_exact_threshold(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeLevelCondition()
        sample_theme.level = 7
        db_session.commit()

        condition = {"type": "theme_level", "theme": sample_theme.name, "value": 7}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_theme_level_entity_not_found_returns_false(self, db_session, sample_user) -> None:
        evaluator = ThemeLevelCondition()
        condition = {"type": "theme_level", "theme": "Missing", "value": 1}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_theme_level_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = ThemeLevelCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "theme_level", "theme": "Education"})

    def test_theme_level_edge_case_1(self, db_session, sample_user) -> None:
        evaluator = ThemeLevelCondition()
        other_user = _create_user(db_session)
        other_theme = Theme(user_id=other_user.id, name="OnlyOther")
        db_session.add(other_theme)
        db_session.commit()

        condition = {"type": "theme_level", "theme": "OnlyOther", "value": 1}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_theme_level_edge_case_2(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeLevelCondition()
        sample_theme.level = 0
        db_session.commit()

        condition = {"type": "theme_level", "theme": sample_theme.name, "value": 0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_theme_level_with_multiple_users(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeLevelCondition()
        sample_theme.level = 1
        other_user = _create_user(db_session)
        other_theme = Theme(user_id=other_user.id, name=sample_theme.name, level=10)
        db_session.add(other_theme)
        db_session.commit()

        condition = {"type": "theme_level", "theme": sample_theme.name, "value": 5}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_theme_level_does_not_mutate_condition(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeLevelCondition()
        sample_theme.level = 2
        db_session.commit()

        condition = {"type": "theme_level", "theme": sample_theme.name, "value": 1}
        original = condition.copy()

        evaluator.evaluate(db_session, sample_user.id, condition)

        assert condition == original


class TestSkillLevelCondition:
    def test_skill_level_met(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillLevelCondition()
        sample_skill.level = 12
        db_session.commit()

        condition = {"type": "skill_level", "skill": sample_skill.name, "value": 5}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_skill_level_not_met(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillLevelCondition()
        sample_skill.level = 2
        db_session.commit()

        condition = {"type": "skill_level", "skill": sample_skill.name, "value": 5}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_skill_level_exact_threshold(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillLevelCondition()
        sample_skill.level = 9
        db_session.commit()

        condition = {"type": "skill_level", "skill": sample_skill.name, "value": 9}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_skill_level_entity_not_found_returns_false(self, db_session, sample_user) -> None:
        evaluator = SkillLevelCondition()
        condition = {"type": "skill_level", "skill": "Missing", "value": 1}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_skill_level_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = SkillLevelCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "skill_level", "skill": "Python"})

    def test_skill_level_edge_case_1(self, db_session, sample_user) -> None:
        evaluator = SkillLevelCondition()
        other_user = _create_user(db_session)
        other_skill = Skill(user_id=other_user.id, name="OnlyOther", level=10)
        db_session.add(other_skill)
        db_session.commit()

        condition = {"type": "skill_level", "skill": "OnlyOther", "value": 1}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_skill_level_edge_case_2(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillLevelCondition()
        sample_skill.level = 0
        db_session.commit()

        condition = {"type": "skill_level", "skill": sample_skill.name, "value": 0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_skill_level_with_multiple_users(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillLevelCondition()
        sample_skill.level = 1
        other_user = _create_user(db_session)
        other_skill = Skill(user_id=other_user.id, name=sample_skill.name, level=10)
        db_session.add(other_skill)
        db_session.commit()

        condition = {"type": "skill_level", "skill": sample_skill.name, "value": 5}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False


class TestTotalXPCondition:
    def test_total_xp_met(self, db_session, sample_user, sample_theme) -> None:
        evaluator = TotalXPCondition()
        sample_theme.xp = 60.0
        extra_theme = Theme(user_id=sample_user.id, name="Second", xp=50.0)
        db_session.add(extra_theme)
        db_session.commit()

        condition = {"type": "total_xp", "value": 100.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_total_xp_not_met(self, db_session, sample_user, sample_theme) -> None:
        evaluator = TotalXPCondition()
        sample_theme.xp = 20.0
        extra_theme = Theme(user_id=sample_user.id, name="Second", xp=30.0)
        db_session.add(extra_theme)
        db_session.commit()

        condition = {"type": "total_xp", "value": 100.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_total_xp_exact_threshold(self, db_session, sample_user, sample_theme) -> None:
        evaluator = TotalXPCondition()
        sample_theme.xp = 25.0
        extra_theme = Theme(user_id=sample_user.id, name="Second", xp=75.0)
        db_session.add(extra_theme)
        db_session.commit()

        condition = {"type": "total_xp", "value": 100.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_total_xp_entity_not_found_returns_false(self, db_session) -> None:
        evaluator = TotalXPCondition()
        other_user = _create_user(db_session)
        condition = {"type": "total_xp", "value": 1.0}

        assert evaluator.evaluate(db_session, other_user.id, condition) is False

    def test_total_xp_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = TotalXPCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "total_xp"})

    def test_total_xp_edge_case_1(self, db_session, sample_user, sample_theme) -> None:
        evaluator = TotalXPCondition()
        sample_theme.xp = 5.0
        other_user = _create_user(db_session)
        other_theme = Theme(user_id=other_user.id, name="Other", xp=999.0)
        db_session.add(other_theme)
        db_session.commit()

        condition = {"type": "total_xp", "value": 100.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_total_xp_edge_case_2(self, db_session, sample_user, sample_theme) -> None:
        evaluator = TotalXPCondition()
        sample_theme.xp = 10.5
        extra_theme = Theme(user_id=sample_user.id, name="Second", xp=9.5)
        db_session.add(extra_theme)
        db_session.commit()

        condition = {"type": "total_xp", "value": 20.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_total_xp_with_multiple_users(self, db_session, sample_user, sample_theme) -> None:
        evaluator = TotalXPCondition()
        sample_theme.xp = 10.0
        other_user = _create_user(db_session)
        other_theme = Theme(user_id=other_user.id, name="Other", xp=200.0)
        db_session.add(other_theme)
        db_session.commit()

        condition = {"type": "total_xp", "value": 100.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False


class TestThemeXPCondition:
    def test_theme_xp_met(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeXPCondition()
        sample_theme.xp = 1000.0
        db_session.commit()

        condition = {"type": "theme_xp", "theme": sample_theme.name, "value": 1000.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_theme_xp_not_met(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeXPCondition()
        sample_theme.xp = 500.0
        db_session.commit()

        condition = {"type": "theme_xp", "theme": sample_theme.name, "value": 1000.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_theme_xp_exact_threshold(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeXPCondition()
        sample_theme.xp = 250.0
        db_session.commit()

        condition = {"type": "theme_xp", "theme": sample_theme.name, "value": 250.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_theme_xp_entity_not_found_returns_false(self, db_session, sample_user) -> None:
        evaluator = ThemeXPCondition()
        condition = {"type": "theme_xp", "theme": "Missing", "value": 1}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_theme_xp_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = ThemeXPCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "theme_xp", "value": 10})

    def test_theme_xp_edge_case_1(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeXPCondition()
        sample_theme.xp = 10.0
        other_user = _create_user(db_session)
        other_theme = Theme(user_id=other_user.id, name=sample_theme.name, xp=500.0)
        db_session.add(other_theme)
        db_session.commit()

        condition = {"type": "theme_xp", "theme": sample_theme.name, "value": 100.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_theme_xp_edge_case_2(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeXPCondition()
        sample_theme.xp = 0.0
        db_session.commit()

        condition = {"type": "theme_xp", "theme": sample_theme.name, "value": 0.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_theme_xp_with_multiple_users(self, db_session, sample_user, sample_theme) -> None:
        evaluator = ThemeXPCondition()
        sample_theme.xp = 25.0
        other_user = _create_user(db_session)
        other_theme = Theme(user_id=other_user.id, name=sample_theme.name, xp=200.0)
        db_session.add(other_theme)
        db_session.commit()

        condition = {"type": "theme_xp", "theme": sample_theme.name, "value": 100.0}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False


class TestQuestCompletionCountCondition:
    def test_quest_completion_count_met(self, db_session, sample_user) -> None:
        evaluator = QuestCompletionCountCondition()
        _create_quest(db_session, sample_user.id, status="completed")
        _create_quest(db_session, sample_user.id, status="completed")

        condition = {"type": "quest_completion_count", "value": 2}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_quest_completion_count_not_met(self, db_session, sample_user) -> None:
        evaluator = QuestCompletionCountCondition()
        _create_quest(db_session, sample_user.id, status="completed")

        condition = {"type": "quest_completion_count", "value": 2}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_quest_completion_count_exact_threshold(self, db_session, sample_user) -> None:
        evaluator = QuestCompletionCountCondition()
        for _ in range(3):
            _create_quest(db_session, sample_user.id, status="completed")

        condition = {"type": "quest_completion_count", "value": 3}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_quest_completion_count_entity_not_found_returns_false(self, db_session) -> None:
        evaluator = QuestCompletionCountCondition()
        other_user = _create_user(db_session)
        condition = {"type": "quest_completion_count", "value": 1}

        assert evaluator.evaluate(db_session, other_user.id, condition) is False

    def test_quest_completion_count_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = QuestCompletionCountCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "quest_completion_count"})

    def test_quest_completion_count_edge_case_1(self, db_session, sample_user) -> None:
        evaluator = QuestCompletionCountCondition()
        _create_quest(db_session, sample_user.id, status="completed")
        _create_quest(db_session, sample_user.id, status="failed")
        _create_quest(db_session, sample_user.id, status="in_progress")

        condition = {"type": "quest_completion_count", "value": 2}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_quest_completion_count_edge_case_2(self, db_session, sample_user) -> None:
        evaluator = QuestCompletionCountCondition()
        other_user = _create_user(db_session)
        for _ in range(3):
            _create_quest(db_session, other_user.id, status="completed")

        condition = {"type": "quest_completion_count", "value": 1}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_quest_completion_count_with_multiple_users(self, db_session, sample_user) -> None:
        evaluator = QuestCompletionCountCondition()
        _create_quest(db_session, sample_user.id, status="completed")
        other_user = _create_user(db_session)
        for _ in range(5):
            _create_quest(db_session, other_user.id, status="completed")

        condition = {"type": "quest_completion_count", "value": 2}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False


class TestSpecificQuestCompletedCondition:
    def test_specific_quest_completed_met(self, db_session, sample_user) -> None:
        evaluator = SpecificQuestCompletedCondition()
        quest = _create_quest(db_session, sample_user.id, status="completed")

        condition = {"type": "specific_quest_completed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_specific_quest_completed_not_met(self, db_session, sample_user) -> None:
        evaluator = SpecificQuestCompletedCondition()
        quest = _create_quest(db_session, sample_user.id, status="in_progress")

        condition = {"type": "specific_quest_completed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_specific_quest_completed_exact_threshold(self, db_session, sample_user) -> None:
        evaluator = SpecificQuestCompletedCondition()
        quest = _create_quest(db_session, sample_user.id, status="completed")

        condition = {"type": "specific_quest_completed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_specific_quest_completed_entity_not_found_returns_false(self, db_session, sample_user) -> None:
        evaluator = SpecificQuestCompletedCondition()
        condition = {"type": "specific_quest_completed", "quest_id": "missing"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_specific_quest_completed_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = SpecificQuestCompletedCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "specific_quest_completed"})

    def test_specific_quest_completed_edge_case_1(self, db_session, sample_user) -> None:
        evaluator = SpecificQuestCompletedCondition()
        other_user = _create_user(db_session)
        quest = _create_quest(db_session, other_user.id, status="completed")

        condition = {"type": "specific_quest_completed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_specific_quest_completed_edge_case_2(self, db_session, sample_user) -> None:
        evaluator = SpecificQuestCompletedCondition()
        quest = _create_quest(db_session, sample_user.id, status="COMPLETED")

        condition = {"type": "specific_quest_completed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_specific_quest_completed_with_multiple_users(self, db_session, sample_user) -> None:
        evaluator = SpecificQuestCompletedCondition()
        quest = _create_quest(db_session, sample_user.id, status="completed")
        other_user = _create_user(db_session)
        _create_quest(db_session, other_user.id, status="in_progress")

        condition = {"type": "specific_quest_completed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True


class TestSkillRankCondition:
    def test_skill_rank_met(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillRankCondition()
        sample_skill.rank = "Expert"
        db_session.commit()

        condition = {"type": "skill_rank", "rank": "Expert"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_skill_rank_not_met(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillRankCondition()
        sample_skill.rank = "Beginner"
        db_session.commit()

        condition = {"type": "skill_rank", "rank": "Expert"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_skill_rank_exact_threshold(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillRankCondition()
        sample_skill.rank = "Intermediate"
        db_session.commit()

        condition = {"type": "skill_rank", "rank": "Intermediate"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_skill_rank_entity_not_found_returns_false(self, db_session) -> None:
        evaluator = SkillRankCondition()
        other_user = _create_user(db_session)
        condition = {"type": "skill_rank", "rank": "Expert"}

        assert evaluator.evaluate(db_session, other_user.id, condition) is False

    def test_skill_rank_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = SkillRankCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "skill_rank"})

    def test_skill_rank_edge_case_1(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillRankCondition()
        sample_skill.rank = "Beginner"
        extra_skill = Skill(user_id=sample_user.id, name="Extra", rank="Master")
        db_session.add(extra_skill)
        db_session.commit()

        condition = {"type": "skill_rank", "rank": "Master"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_skill_rank_edge_case_2(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillRankCondition()
        sample_skill.rank = "Expert"
        db_session.commit()

        condition = {"type": "skill_rank", "rank": "expert"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_skill_rank_with_multiple_users(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillRankCondition()
        sample_skill.rank = "Beginner"
        other_user = _create_user(db_session)
        other_skill = Skill(user_id=other_user.id, name="Other", rank="Expert")
        db_session.add(other_skill)
        db_session.commit()

        condition = {"type": "skill_rank", "rank": "Expert"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_skill_rank_invalid_rank_returns_false(self, db_session, sample_user, sample_skill) -> None:
        evaluator = SkillRankCondition()
        sample_skill.rank = "Expert"
        db_session.commit()

        condition = {"type": "skill_rank", "rank": "Legend"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False


class TestJournalCountCondition:
    def test_journal_count_met(self, db_session, sample_user) -> None:
        evaluator = JournalCountCondition()
        for _ in range(5):
            _create_journal_entry(db_session, sample_user.id)

        condition = {"type": "journal_count", "value": 3}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_journal_count_not_met(self, db_session, sample_user) -> None:
        evaluator = JournalCountCondition()
        _create_journal_entry(db_session, sample_user.id)

        condition = {"type": "journal_count", "value": 3}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_journal_count_exact_threshold(self, db_session, sample_user) -> None:
        evaluator = JournalCountCondition()
        for _ in range(3):
            _create_journal_entry(db_session, sample_user.id)

        condition = {"type": "journal_count", "value": 3}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_journal_count_entity_not_found_returns_false(self, db_session, sample_user) -> None:
        evaluator = JournalCountCondition()
        condition = {"type": "journal_count", "value": 1}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_journal_count_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = JournalCountCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "journal_count"})

    def test_journal_count_edge_case_1(self, db_session, sample_user) -> None:
        evaluator = JournalCountCondition()
        same_day = datetime(2025, 6, 1, 9, 0, 0)
        _create_journal_entry(db_session, sample_user.id, same_day)
        _create_journal_entry(db_session, sample_user.id, same_day + timedelta(hours=1))

        condition = {"type": "journal_count", "value": 2}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_journal_count_edge_case_2(self, db_session, sample_user) -> None:
        evaluator = JournalCountCondition()
        other_user = _create_user(db_session)
        _create_journal_entry(db_session, other_user.id)

        condition = {"type": "journal_count", "value": 1}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_journal_count_with_multiple_users(self, db_session, sample_user) -> None:
        evaluator = JournalCountCondition()
        _create_journal_entry(db_session, sample_user.id)
        other_user = _create_user(db_session)
        for _ in range(4):
            _create_journal_entry(db_session, other_user.id)

        condition = {"type": "journal_count", "value": 2}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False


class TestTimeBasedCondition:
    def test_time_based_met(self, db_session, sample_user) -> None:
        evaluator = TimeBasedCondition()
        with freeze_time("2025-01-01"):
            _create_journal_entry(db_session, sample_user.id)
        with freeze_time("2025-01-02"):
            _create_journal_entry(db_session, sample_user.id)
        with freeze_time("2025-01-03"):
            _create_journal_entry(db_session, sample_user.id)

        condition = {"type": "time_based", "days_active": 3}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_time_based_not_met(self, db_session, sample_user) -> None:
        evaluator = TimeBasedCondition()
        with freeze_time("2025-02-01"):
            _create_journal_entry(db_session, sample_user.id)
        with freeze_time("2025-02-02"):
            _create_journal_entry(db_session, sample_user.id)

        condition = {"type": "time_based", "days_active": 3}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_time_based_exact_threshold(self, db_session, sample_user) -> None:
        evaluator = TimeBasedCondition()
        with freeze_time("2025-03-01"):
            _create_journal_entry(db_session, sample_user.id)
        with freeze_time("2025-03-02"):
            _create_journal_entry(db_session, sample_user.id)

        condition = {"type": "time_based", "days_active": 2}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_time_based_entity_not_found_returns_false(self, db_session, sample_user) -> None:
        evaluator = TimeBasedCondition()
        condition = {"type": "time_based", "days_active": 1}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_time_based_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = TimeBasedCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "time_based"})

    def test_time_based_edge_case_1(self, db_session, sample_user) -> None:
        evaluator = TimeBasedCondition()
        with freeze_time("2025-04-01"):
            _create_journal_entry(db_session, sample_user.id)
            _create_journal_entry(db_session, sample_user.id)
        with freeze_time("2025-04-02"):
            _create_journal_entry(db_session, sample_user.id)

        condition = {"type": "time_based", "days_active": 2}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_time_based_edge_case_2(self, db_session, sample_user) -> None:
        evaluator = TimeBasedCondition()
        with freeze_time("2025-05-01"):
            _create_journal_entry(db_session, sample_user.id)
        with freeze_time("2025-05-03"):
            _create_journal_entry(db_session, sample_user.id)
        with freeze_time("2025-05-07"):
            _create_journal_entry(db_session, sample_user.id)

        condition = {"type": "time_based", "days_active": 3}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_time_based_with_multiple_users(self, db_session, sample_user) -> None:
        evaluator = TimeBasedCondition()
        other_user = _create_user(db_session)
        with freeze_time("2025-06-01"):
            _create_journal_entry(db_session, other_user.id)

        condition = {"type": "time_based", "days_active": 1}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False


class TestCorrosionLevelCondition:
    def test_corrosion_level_met(self, db_session, sample_user) -> None:
        evaluator = CorrosionLevelCondition()
        theme = Theme(user_id=sample_user.id, name="Education", corrosion_level="Rusty")
        db_session.add(theme)
        db_session.commit()

        condition = {"type": "corrosion_level", "theme": "Education", "min_level": "Rusty"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_corrosion_level_not_met(self, db_session, sample_user) -> None:
        evaluator = CorrosionLevelCondition()
        theme = Theme(user_id=sample_user.id, name="Education", corrosion_level="Fresh")
        db_session.add(theme)
        db_session.commit()

        condition = {"type": "corrosion_level", "theme": "Education", "min_level": "Dusty"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_corrosion_level_exact_threshold(self, db_session, sample_user) -> None:
        evaluator = CorrosionLevelCondition()
        theme = Theme(user_id=sample_user.id, name="Education", corrosion_level="Dusty")
        db_session.add(theme)
        db_session.commit()

        condition = {"type": "corrosion_level", "theme": "Education", "min_level": "Dusty"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_corrosion_level_entity_not_found_returns_false(self, db_session, sample_user) -> None:
        evaluator = CorrosionLevelCondition()
        condition = {"type": "corrosion_level", "theme": "Missing", "min_level": "Rusty"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_corrosion_level_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = CorrosionLevelCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "corrosion_level", "theme": "Education"})

    def test_corrosion_level_edge_case_1(self, db_session, sample_user) -> None:
        evaluator = CorrosionLevelCondition()
        theme = Theme(user_id=sample_user.id, name="Education", corrosion_level="Rusty")
        db_session.add(theme)
        db_session.commit()

        condition = {"type": "corrosion_level", "theme": "Education", "min_level": "Unknown"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_corrosion_level_edge_case_2(self, db_session, sample_user) -> None:
        evaluator = CorrosionLevelCondition()
        theme = Theme(user_id=sample_user.id, name="Education", corrosion_level="Broken")
        db_session.add(theme)
        db_session.commit()

        condition = {"type": "corrosion_level", "theme": "Education", "min_level": "Familiar"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_corrosion_level_with_multiple_users(self, db_session, sample_user) -> None:
        evaluator = CorrosionLevelCondition()
        other_user = _create_user(db_session)
        other_theme = Theme(user_id=other_user.id, name="Education", corrosion_level="Forgotten")
        db_session.add(other_theme)
        db_session.commit()

        condition = {"type": "corrosion_level", "theme": "Education", "min_level": "Rusty"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False


class TestQuestFailedCondition:
    def test_quest_failed_met(self, db_session, sample_user) -> None:
        evaluator = QuestFailedCondition()
        quest = _create_quest(db_session, sample_user.id, status="failed")

        condition = {"type": "quest_failed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_quest_failed_not_met(self, db_session, sample_user) -> None:
        evaluator = QuestFailedCondition()
        quest = _create_quest(db_session, sample_user.id, status="completed")

        condition = {"type": "quest_failed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_quest_failed_exact_threshold(self, db_session, sample_user) -> None:
        evaluator = QuestFailedCondition()
        quest = _create_quest(db_session, sample_user.id, status="failed")

        condition = {"type": "quest_failed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_quest_failed_entity_not_found_returns_false(self, db_session, sample_user) -> None:
        evaluator = QuestFailedCondition()
        condition = {"type": "quest_failed", "quest_id": "missing"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_quest_failed_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = QuestFailedCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "quest_failed"})

    def test_quest_failed_edge_case_1(self, db_session, sample_user) -> None:
        evaluator = QuestFailedCondition()
        quest = _create_quest(db_session, sample_user.id, status="FAILED")

        condition = {"type": "quest_failed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_quest_failed_edge_case_2(self, db_session, sample_user) -> None:
        evaluator = QuestFailedCondition()
        other_user = _create_user(db_session)
        quest = _create_quest(db_session, other_user.id, status="failed")

        condition = {"type": "quest_failed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_quest_failed_with_multiple_users(self, db_session, sample_user) -> None:
        evaluator = QuestFailedCondition()
        quest = _create_quest(db_session, sample_user.id, status="failed")
        other_user = _create_user(db_session)
        _create_quest(db_session, other_user.id, status="failed")

        condition = {"type": "quest_failed", "quest_id": quest.id}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True


class TestItemEquippedCondition:
    def test_item_equipped_met(self, db_session, sample_user) -> None:
        evaluator = ItemEquippedCondition()
        template = _create_item_template(db_session, "cursed_item")
        _create_user_item(db_session, sample_user.id, template.id, is_equipped=True)

        condition = {"type": "item_equipped", "item_type": "cursed_item"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_item_equipped_not_met(self, db_session, sample_user) -> None:
        evaluator = ItemEquippedCondition()
        template = _create_item_template(db_session, "cursed_item")
        _create_user_item(db_session, sample_user.id, template.id, is_equipped=False)

        condition = {"type": "item_equipped", "item_type": "cursed_item"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_item_equipped_exact_threshold(self, db_session, sample_user) -> None:
        evaluator = ItemEquippedCondition()
        template = _create_item_template(db_session, "cursed_item")
        _create_user_item(db_session, sample_user.id, template.id, is_equipped=True)

        condition = {"type": "item_equipped", "item_type": "cursed_item"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_item_equipped_entity_not_found_returns_false(self, db_session, sample_user) -> None:
        evaluator = ItemEquippedCondition()
        condition = {"type": "item_equipped", "item_type": "cursed_item"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_item_equipped_missing_required_field_raises_error(self, db_session, sample_user) -> None:
        evaluator = ItemEquippedCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "item_equipped"})

    def test_item_equipped_edge_case_1(self, db_session, sample_user) -> None:
        evaluator = ItemEquippedCondition()
        template = _create_item_template(db_session, "blessed_item")
        _create_user_item(db_session, sample_user.id, template.id, is_equipped=True)

        condition = {"type": "item_equipped", "item_type": "cursed_item"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_item_equipped_edge_case_2(self, db_session, sample_user) -> None:
        evaluator = ItemEquippedCondition()
        template = _create_item_template(db_session, "cursed_item")
        _create_user_item(db_session, sample_user.id, template.id, is_equipped=False)

        condition = {"type": "item_equipped", "item_type": "cursed_item"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_item_equipped_with_multiple_users(self, db_session, sample_user) -> None:
        evaluator = ItemEquippedCondition()
        template = _create_item_template(db_session, "cursed_item")
        other_user = _create_user(db_session)
        _create_user_item(db_session, other_user.id, template.id, is_equipped=True)

        condition = {"type": "item_equipped", "item_type": "cursed_item"}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False


class TestCompoundCondition:
    """Tests for compound conditions with AND, OR, NOT logic."""

    # ==========================================================================
    # AND conditions
    # ==========================================================================

    def test_and_all_conditions_true(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        theme = Theme(user_id=sample_user.id, name="Education", level=10, xp=1000.0)
        db_session.add(theme)
        db_session.commit()

        condition = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": "Education", "value": 10},
                {"type": "theme_xp", "theme": "Education", "value": 1000},
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_and_one_condition_false(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        theme = Theme(user_id=sample_user.id, name="Education", level=10, xp=500.0)
        db_session.add(theme)
        db_session.commit()

        condition = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": "Education", "value": 10},
                {"type": "theme_xp", "theme": "Education", "value": 1000},
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_and_all_conditions_false(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        theme = Theme(user_id=sample_user.id, name="Education", level=5, xp=500.0)
        db_session.add(theme)
        db_session.commit()

        condition = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": "Education", "value": 10},
                {"type": "theme_xp", "theme": "Education", "value": 1000},
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_and_empty_conditions_returns_true(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        condition = {"type": "and", "conditions": []}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_and_missing_conditions_raises_error(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "and"})

    # ==========================================================================
    # OR conditions
    # ==========================================================================

    def test_or_all_conditions_true(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        theme = Theme(user_id=sample_user.id, name="Education", level=10, xp=1000.0)
        db_session.add(theme)
        db_session.commit()

        condition = {
            "type": "or",
            "conditions": [
                {"type": "theme_level", "theme": "Education", "value": 10},
                {"type": "theme_xp", "theme": "Education", "value": 1000},
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_or_one_condition_true(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        theme = Theme(user_id=sample_user.id, name="Education", level=10, xp=500.0)
        db_session.add(theme)
        db_session.commit()

        condition = {
            "type": "or",
            "conditions": [
                {"type": "theme_level", "theme": "Education", "value": 10},
                {"type": "theme_xp", "theme": "Education", "value": 1000},
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_or_all_conditions_false(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        theme = Theme(user_id=sample_user.id, name="Education", level=5, xp=500.0)
        db_session.add(theme)
        db_session.commit()

        condition = {
            "type": "or",
            "conditions": [
                {"type": "theme_level", "theme": "Education", "value": 10},
                {"type": "theme_xp", "theme": "Education", "value": 1000},
            ],
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_or_empty_conditions_returns_false(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        condition = {"type": "or", "conditions": []}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_or_missing_conditions_raises_error(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "or"})

    # ==========================================================================
    # NOT conditions
    # ==========================================================================

    def test_not_condition_false_returns_true(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        quest = _create_quest(db_session, sample_user.id, status="completed")

        condition = {
            "type": "not",
            "condition": {"type": "quest_failed", "quest_id": quest.id},
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_not_condition_true_returns_false(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        quest = _create_quest(db_session, sample_user.id, status="failed")

        condition = {
            "type": "not",
            "condition": {"type": "quest_failed", "quest_id": quest.id},
        }

        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_not_missing_condition_raises_error(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"type": "not"})

    # ==========================================================================
    # Nested compound conditions
    # ==========================================================================

    def test_nested_and_with_or(self, db_session, sample_user) -> None:
        """AND with nested OR: theme_level AND (skill_rank OR total_xp)"""
        evaluator = CompoundCondition()
        theme = Theme(user_id=sample_user.id, name="Education", level=10, xp=5000.0)
        skill = Skill(user_id=sample_user.id, name="Python", rank="Intermediate")
        db_session.add_all([theme, skill])
        db_session.commit()

        condition = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": "Education", "value": 10},
                {
                    "type": "or",
                    "conditions": [
                        {"type": "skill_rank", "rank": "Expert"},
                        {"type": "total_xp", "value": 5000},
                    ],
                },
            ],
        }

        # theme_level=10 is True, skill_rank != Expert but total_xp >= 5000
        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_nested_and_with_or_all_false(self, db_session, sample_user) -> None:
        """AND with nested OR where inner OR is false"""
        evaluator = CompoundCondition()
        theme = Theme(user_id=sample_user.id, name="Education", level=10, xp=1000.0)
        skill = Skill(user_id=sample_user.id, name="Python", rank="Intermediate")
        db_session.add_all([theme, skill])
        db_session.commit()

        condition = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": "Education", "value": 10},
                {
                    "type": "or",
                    "conditions": [
                        {"type": "skill_rank", "rank": "Expert"},
                        {"type": "total_xp", "value": 5000},
                    ],
                },
            ],
        }

        # theme_level=10 is True, but neither skill_rank nor total_xp is met
        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_nested_or_with_and(self, db_session, sample_user) -> None:
        """OR with nested AND: journal_streak OR (theme_level AND skill_rank)"""
        evaluator = CompoundCondition()
        theme = Theme(user_id=sample_user.id, name="Education", level=10, xp=1000.0)
        skill = Skill(user_id=sample_user.id, name="Python", rank="Expert")
        db_session.add_all([theme, skill])
        db_session.commit()

        condition = {
            "type": "or",
            "conditions": [
                {"type": "journal_streak", "value": 30},
                {
                    "type": "and",
                    "conditions": [
                        {"type": "theme_level", "theme": "Education", "value": 10},
                        {"type": "skill_rank", "rank": "Expert"},
                    ],
                },
            ],
        }

        # No journal streak, but theme_level AND skill_rank are both true
        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    def test_nested_not_with_and(self, db_session, sample_user) -> None:
        """NOT with nested AND: NOT (quest_failed AND low_xp)"""
        evaluator = CompoundCondition()
        theme = Theme(user_id=sample_user.id, name="Education", level=5, xp=5000.0)
        quest = _create_quest(db_session, sample_user.id, status="failed")
        db_session.add(theme)
        db_session.commit()

        condition = {
            "type": "not",
            "condition": {
                "type": "and",
                "conditions": [
                    {"type": "quest_failed", "quest_id": quest.id},
                    {"type": "total_xp", "value": 100},
                ],
            },
        }

        # Both inner conditions are true, so NOT returns False
        assert evaluator.evaluate(db_session, sample_user.id, condition) is False

    def test_deeply_nested_conditions(self, db_session, sample_user) -> None:
        """Three levels of nesting"""
        evaluator = CompoundCondition()
        theme = Theme(user_id=sample_user.id, name="Education", level=10, xp=2000.0)
        skill = Skill(user_id=sample_user.id, name="Python", rank="Expert")
        db_session.add_all([theme, skill])
        db_session.commit()

        condition = {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": "Education", "value": 10},
                {
                    "type": "or",
                    "conditions": [
                        {
                            "type": "and",
                            "conditions": [
                                {"type": "skill_rank", "rank": "Expert"},
                                {"type": "total_xp", "value": 1000},
                            ],
                        },
                        {"type": "journal_streak", "value": 100},
                    ],
                },
            ],
        }

        # theme_level=10: True
        # Nested OR: (skill_rank=Expert AND total_xp>=1000) OR journal_streak>=100
        # Inner AND: Expert=True AND 2000>=1000=True => True
        # So OR is True, and overall AND is True
        assert evaluator.evaluate(db_session, sample_user.id, condition) is True

    # ==========================================================================
    # Error handling
    # ==========================================================================

    def test_unknown_compound_type_returns_false(self, db_session, sample_user) -> None:
        """Unknown compound types gracefully return False."""
        evaluator = CompoundCondition()
        result = evaluator.evaluate(
            db_session, sample_user.id, {"type": "xor", "conditions": []}
        )
        assert result is False

    def test_unknown_primitive_type_returns_false(self, db_session, sample_user) -> None:
        """Unknown primitive types in sub-conditions return False."""
        evaluator = CompoundCondition()
        result = evaluator.evaluate(
            db_session,
            sample_user.id,
            {
                "type": "and",
                "conditions": [{"type": "unknown_condition", "value": 10}],
            },
        )
        assert result is False

    def test_missing_type_in_condition_raises_error(self, db_session, sample_user) -> None:
        evaluator = CompoundCondition()
        with pytest.raises(KeyError):
            evaluator.evaluate(db_session, sample_user.id, {"conditions": []})

    def test_compound_condition_delegates_to_evaluator(self, db_session, sample_user, sample_theme) -> None:
        evaluator = CompoundCondition()
        sample_theme.xp = 250.0
        db_session.commit()

        condition = {"type": "total_xp", "value": 100}

        assert evaluator.evaluate(db_session, sample_user.id, condition) is True
