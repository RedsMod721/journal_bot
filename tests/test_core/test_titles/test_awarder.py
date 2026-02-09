"""Tests for the TitleAwarder class."""

from unittest.mock import MagicMock

import pytest

from app.core.events import EventBus
from app.core.titles.awarder import TitleAwarder
from app.core.titles.conditions import CONDITION_EVALUATORS
from app.models.theme import Theme
from app.models.title import TitleTemplate, UserTitle


def _create_title_template(
    db_session,
    name: str,
    unlock_condition: dict,
    rank: str = "D",
) -> TitleTemplate:
    template = TitleTemplate(
        name=name,
        description_template=f"{{user_name}} has earned {name}",
        unlock_condition=unlock_condition,
        rank=rank,
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def awarder(event_bus: EventBus) -> TitleAwarder:
    return TitleAwarder(event_bus)


def test_check_user_unlocks_awards_eligible_titles(
    db_session, sample_user, sample_theme, awarder
) -> None:
    sample_theme.level = 10
    sample_theme.xp = 2000.0
    db_session.commit()

    template1 = _create_title_template(
        db_session,
        name="Scholar",
        unlock_condition={"type": "theme_level", "theme": "Education", "value": 10},
    )
    template2 = _create_title_template(
        db_session,
        name="XP Master",
        unlock_condition={"type": "total_xp", "value": 1000},
    )

    new_titles = awarder.check_user_unlocks(db_session, sample_user.id)

    awarded_ids = {title.title_template_id for title in new_titles}
    assert awarded_ids == {template1.id, template2.id}


def test_check_user_unlocks_skips_already_owned(
    db_session, sample_user, sample_theme, awarder
) -> None:
    sample_theme.level = 10
    sample_theme.xp = 1500.0
    db_session.commit()

    template = _create_title_template(
        db_session,
        name="Scholar",
        unlock_condition={"type": "theme_level", "theme": "Education", "value": 10},
    )

    awarder.check_user_unlocks(db_session, sample_user.id)
    new_titles = awarder.check_user_unlocks(db_session, sample_user.id)

    assert new_titles == []

    user_titles = (
        db_session.query(UserTitle)
        .filter(
            UserTitle.user_id == sample_user.id,
            UserTitle.title_template_id == template.id,
        )
        .all()
    )
    assert len(user_titles) == 1


def test_check_user_unlocks_evaluates_all_conditions(
    db_session, sample_user, awarder
) -> None:
    template1 = _create_title_template(
        db_session,
        name="Title One",
        unlock_condition={"type": "theme_level", "theme": "Education", "value": 1},
    )
    template2 = _create_title_template(
        db_session,
        name="Title Two",
        unlock_condition={"type": "total_xp", "value": 100},
    )
    template3 = _create_title_template(
        db_session,
        name="Title Three",
        unlock_condition={"type": "journal_count", "value": 5},
    )

    awarder._evaluate_condition = MagicMock(side_effect=[False, False, True])
    awarder.award_title = MagicMock(return_value=MagicMock())

    new_titles = awarder.check_user_unlocks(db_session, sample_user.id)

    assert awarder._evaluate_condition.call_count == 3
    awarder._evaluate_condition.assert_any_call(
        db_session, sample_user.id, template1.unlock_condition
    )
    awarder._evaluate_condition.assert_any_call(
        db_session, sample_user.id, template2.unlock_condition
    )
    awarder._evaluate_condition.assert_any_call(
        db_session, sample_user.id, template3.unlock_condition
    )
    assert len(new_titles) == 1
    awarder.award_title.assert_called_once()


def test_check_user_unlocks_emits_events_for_each_unlock(
    db_session, sample_user, sample_theme, event_bus
) -> None:
    awarder = TitleAwarder(event_bus)
    event_bus.emit = MagicMock()

    sample_theme.level = 10
    sample_theme.xp = 2000.0
    db_session.commit()

    _create_title_template(
        db_session,
        name="Scholar",
        unlock_condition={"type": "theme_level", "theme": "Education", "value": 10},
    )
    _create_title_template(
        db_session,
        name="XP Master",
        unlock_condition={"type": "total_xp", "value": 1000},
    )

    awarder.check_user_unlocks(db_session, sample_user.id)

    assert event_bus.emit.call_count == 2


def test_check_user_unlocks_handles_compound_conditions(
    db_session, sample_user, sample_theme, awarder
) -> None:
    sample_theme.level = 10
    sample_theme.xp = 2500.0
    db_session.commit()

    template = _create_title_template(
        db_session,
        name="Dedicated Scholar",
        unlock_condition={
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": "Education", "value": 10},
                {"type": "total_xp", "value": 2000},
            ],
        },
    )

    new_titles = awarder.check_user_unlocks(db_session, sample_user.id)

    assert len(new_titles) == 1
    assert new_titles[0].title_template_id == template.id


def test_check_user_unlocks_awards_negative_titles(
    db_session, sample_user, sample_theme, awarder
) -> None:
    sample_theme.corrosion_level = "Rusty"
    db_session.commit()

    template = _create_title_template(
        db_session,
        name="Neglected",
        unlock_condition={
            "type": "corrosion_level",
            "theme": "Education",
            "min_level": "Dusty",
        },
    )

    new_titles = awarder.check_user_unlocks(db_session, sample_user.id)

    assert len(new_titles) == 1
    assert new_titles[0].title_template_id == template.id


def test_check_user_unlocks_does_not_award_unmet_condition(
    db_session, sample_user, sample_theme, awarder
) -> None:
    sample_theme.level = 5
    db_session.commit()

    _create_title_template(
        db_session,
        name="Scholar",
        unlock_condition={"type": "theme_level", "theme": "Education", "value": 10},
    )

    new_titles = awarder.check_user_unlocks(db_session, sample_user.id)

    assert new_titles == []


def test_check_user_unlocks_skips_empty_conditions(
    db_session, sample_user, awarder
) -> None:
    _create_title_template(
        db_session,
        name="Empty Condition",
        unlock_condition={},
    )

    new_titles = awarder.check_user_unlocks(db_session, sample_user.id)

    assert new_titles == []


def test_award_title_creates_user_title(
    db_session, sample_user, awarder
) -> None:
    template = _create_title_template(
        db_session,
        name="Test Title",
        unlock_condition={"type": "total_xp", "value": 100},
    )

    user_title = awarder.award_title(
        db_session, sample_user.id, template.id, "manual_grant"
    )

    assert user_title.user_id == sample_user.id
    assert user_title.title_template_id == template.id


def test_award_title_auto_equips_first_title(
    db_session, sample_user, awarder
) -> None:
    template = _create_title_template(
        db_session,
        name="First Title",
        unlock_condition={"type": "total_xp", "value": 100},
    )

    user_title = awarder.award_title(
        db_session, sample_user.id, template.id, "manual_grant"
    )

    assert user_title.is_equipped is True


def test_award_title_doesnt_auto_equip_subsequent_titles(
    db_session, sample_user, awarder
) -> None:
    template1 = _create_title_template(
        db_session,
        name="First Title",
        unlock_condition={"type": "total_xp", "value": 100},
    )
    template2 = _create_title_template(
        db_session,
        name="Second Title",
        unlock_condition={"type": "total_xp", "value": 200},
    )

    awarder.award_title(db_session, sample_user.id, template1.id, "manual_grant")
    user_title2 = awarder.award_title(
        db_session, sample_user.id, template2.id, "manual_grant"
    )

    assert user_title2.is_equipped is False


def test_evaluate_condition_routes_to_correct_evaluator(
    db_session, sample_user, awarder
) -> None:
    evaluator = MagicMock()
    evaluator.evaluate = MagicMock(return_value=True)
    awarder._evaluators["theme_level"] = evaluator

    condition = {"type": "theme_level", "theme": "Education", "value": 1}

    result = awarder._evaluate_condition(db_session, sample_user.id, condition)

    assert result is True
    evaluator.evaluate.assert_called_once_with(db_session, sample_user.id, condition)


def test_evaluate_condition_handles_unknown_type_gracefully(
    db_session, sample_user, awarder
) -> None:
    result = awarder._evaluate_condition(
        db_session, sample_user.id, {"type": "unknown_type", "value": 10}
    )

    assert result is False


def test_evaluate_condition_handles_evaluator_exception(
    db_session, sample_user, awarder
) -> None:
    failing_evaluator = MagicMock()
    failing_evaluator.evaluate.side_effect = RuntimeError("boom")
    awarder._evaluators["theme_level"] = failing_evaluator

    result = awarder._evaluate_condition(
        db_session,
        sample_user.id,
        {"type": "theme_level", "theme": "Education", "value": 1},
    )

    assert result is False


def test_evaluate_condition_handles_missing_type(
    db_session, sample_user, awarder
) -> None:
    result = awarder._evaluate_condition(db_session, sample_user.id, {"value": 10})

    assert result is False


def test_evaluate_condition_handles_empty_condition(
    db_session, sample_user, awarder
) -> None:
    result = awarder._evaluate_condition(db_session, sample_user.id, {})

    assert result is False


def test_register_evaluators_includes_all_types(awarder) -> None:
    evaluators = awarder._register_evaluators()

    assert set(evaluators.keys()) == set(CONDITION_EVALUATORS.keys())
