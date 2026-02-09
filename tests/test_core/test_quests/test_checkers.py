"""Tests for quest completion checkers."""

from app.core.quests.checkers import YesNoChecker
from app.models.mission_quest import UserMissionQuest


def _create_user_quest(db_session, user_id: str, progress: int = 0, status: str = "not_started") -> UserMissionQuest:
    quest = UserMissionQuest(
        user_id=user_id,
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
