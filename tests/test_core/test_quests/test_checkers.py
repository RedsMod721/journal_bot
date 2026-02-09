"""Tests for quest completion checkers."""

import pytest

from app.core.quests.checkers import AccumulationChecker, YesNoChecker
from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest


def _create_template(db_session, completion_condition: dict) -> MissionQuestTemplate:
    template = MissionQuestTemplate(
        name="Template",
        completion_condition=completion_condition,
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


def _create_user_quest(
    db_session,
    user_id: str,
    progress: int = 0,
    status: str = "not_started",
    template: MissionQuestTemplate | None = None,
) -> UserMissionQuest:
    quest = UserMissionQuest(
        user_id=user_id,
        template_id=template.id if template else None,
        name="Daily Check",
        completion_progress=progress,
        status=status,
    )
    db_session.add(quest)
    db_session.commit()
    db_session.refresh(quest)
    return quest


def test_yes_no_checker_manual_completion_true(db_session, sample_user) -> None:
    checker = YesNoChecker()
    user_quest = _create_user_quest(db_session, sample_user.id, progress=0)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"manual_completion": True},
    )

    assert is_complete is True
    assert new_progress == 100


def test_yes_no_checker_manual_completion_false(db_session, sample_user) -> None:
    checker = YesNoChecker()
    user_quest = _create_user_quest(db_session, sample_user.id, progress=20)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"manual_completion": False},
    )

    assert is_complete is False
    assert new_progress == 20


def test_yes_no_checker_no_manual_flag_returns_false(db_session, sample_user) -> None:
    checker = YesNoChecker()
    user_quest = _create_user_quest(db_session, sample_user.id, progress=10)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {},
    )

    assert is_complete is False
    assert new_progress == 10


def test_yes_no_checker_already_completed_stays_completed(db_session, sample_user) -> None:
    checker = YesNoChecker()
    user_quest = _create_user_quest(db_session, sample_user.id, progress=100, status="completed")

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {},
    )

    assert is_complete is True
    assert new_progress == 100


def test_yes_no_checker_sets_progress_to_100_on_completion(db_session, sample_user) -> None:
    checker = YesNoChecker()
    user_quest = _create_user_quest(db_session, sample_user.id, progress=40)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"manual_completion": True},
    )

    assert is_complete is True
    assert new_progress == 100


def test_yes_no_checker_context_quest_completed_true(db_session, sample_user) -> None:
    checker = YesNoChecker()
    user_quest = _create_user_quest(db_session, sample_user.id, progress=0)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"quest_completed": True},
    )

    assert is_complete is True
    assert new_progress == 100


def test_yes_no_checker_context_completed_true_alias(db_session, sample_user) -> None:
    checker = YesNoChecker()
    user_quest = _create_user_quest(db_session, sample_user.id, progress=5)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"completed": True},
    )

    assert is_complete is True
    assert new_progress == 100


def test_accumulation_checker_adds_to_progress(db_session, sample_user) -> None:
    checker = AccumulationChecker()
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 50, "unit": "minutes"},
    )
    user_quest = _create_user_quest(db_session, sample_user.id, progress=10, template=template)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"detected_minutes": 5},
    )

    assert is_complete is False
    assert new_progress == 15


def test_accumulation_checker_reaches_target(db_session, sample_user) -> None:
    checker = AccumulationChecker()
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 50, "unit": "minutes"},
    )
    user_quest = _create_user_quest(db_session, sample_user.id, progress=20, template=template)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"detected_minutes": 30},
    )

    assert is_complete is True
    assert new_progress == 50


def test_accumulation_checker_exceeds_target_caps_at_target(db_session, sample_user) -> None:
    checker = AccumulationChecker()
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 50, "unit": "minutes"},
    )
    user_quest = _create_user_quest(db_session, sample_user.id, progress=40, template=template)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"detected_minutes": 20},
    )

    assert is_complete is True
    assert new_progress == 50


def test_accumulation_checker_no_amount_in_context_returns_current(db_session, sample_user) -> None:
    checker = AccumulationChecker()
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 50, "unit": "minutes"},
    )
    user_quest = _create_user_quest(db_session, sample_user.id, progress=12, template=template)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {},
    )

    assert is_complete is False
    assert new_progress == 12


@pytest.mark.parametrize(
    "unit,context_key",
    [
        ("minutes", "detected_minutes"),
        ("count", "detected_count"),
        ("pages", "detected_pages"),
    ],
)
def test_accumulation_checker_different_units(
    db_session,
    sample_user,
    unit,
    context_key,
) -> None:
    checker = AccumulationChecker()
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 10, "unit": unit},
    )
    user_quest = _create_user_quest(db_session, sample_user.id, progress=0, template=template)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {context_key: 3},
    )

    assert is_complete is False
    assert new_progress == 3


def test_accumulation_checker_handles_float_amounts(db_session, sample_user) -> None:
    checker = AccumulationChecker()
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 50, "unit": "minutes"},
    )
    user_quest = _create_user_quest(db_session, sample_user.id, progress=10, template=template)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"detected_minutes": 2.5},
    )

    assert is_complete is False
    assert new_progress == 12


def test_accumulation_checker_zero_amount_doesnt_change_progress(db_session, sample_user) -> None:
    checker = AccumulationChecker()
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 50, "unit": "minutes"},
    )
    user_quest = _create_user_quest(db_session, sample_user.id, progress=7, template=template)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"detected_minutes": 0},
    )

    assert is_complete is False
    assert new_progress == 7


def test_accumulation_checker_multiple_increments_accumulate(db_session, sample_user) -> None:
    checker = AccumulationChecker()
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 50, "unit": "minutes"},
    )
    user_quest = _create_user_quest(db_session, sample_user.id, progress=10, template=template)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"detected_minutes": 15},
    )

    assert is_complete is False
    assert new_progress == 25

    user_quest.completion_progress = new_progress

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"detected_minutes": 20},
    )

    assert is_complete is False
    assert new_progress == 45


def test_accumulation_checker_uses_detected_amount_fallback(db_session, sample_user) -> None:
    checker = AccumulationChecker()
    template = _create_template(
        db_session,
        {"type": "accumulation", "target": 50, "unit": "minutes"},
    )
    user_quest = _create_user_quest(db_session, sample_user.id, progress=10, template=template)

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"detected_amount": 12},
    )

    assert is_complete is False
    assert new_progress == 22


def test_accumulation_checker_uses_completion_target_when_no_template(db_session, sample_user) -> None:
    checker = AccumulationChecker()
    user_quest = _create_user_quest(db_session, sample_user.id, progress=90)
    user_quest.completion_target = 100

    is_complete, new_progress = checker.check_completion(
        db_session,
        user_quest,
        {"detected_count": 15},
    )

    assert is_complete is True
    assert new_progress == 100
