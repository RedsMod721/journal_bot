"""Unit tests for src.core.quests."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.core.quests import check_quest_match, update_quest_progress


def _make_entry(dt: datetime, content: str = "") -> SimpleNamespace:
    return SimpleNamespace(created_at=dt, content=content)


def _make_skill(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def test_streak_match_does_not_require_updated_at_field() -> None:
    quest = SimpleNamespace(
        id="q1",
        name="Code Daily",
        completion_type="streak",
        skill=_make_skill("Python Programming"),
        current_progress=1,
        required_progress=30,
        updated_at_utc_ms=None,
        created_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    entry = _make_entry(datetime(2026, 2, 21, tzinfo=timezone.utc))

    assert check_quest_match(quest, entry, ["Python Programming"], ["coded"]) is True


def test_streak_match_dedupes_same_day_using_updated_at_utc_ms() -> None:
    quest = SimpleNamespace(
        id="q2",
        name="Code Daily",
        completion_type="streak",
        skill=_make_skill("Python Programming"),
        current_progress=5,
        required_progress=30,
        updated_at_utc_ms=int(
            datetime(2026, 2, 22, 10, tzinfo=timezone.utc).timestamp() * 1000
        ),
        created_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    entry = _make_entry(datetime(2026, 2, 22, 18, tzinfo=timezone.utc))

    assert check_quest_match(quest, entry, ["Python Programming"], ["coded"]) is False


def test_one_time_keyword_and_activity_matching() -> None:
    quest = SimpleNamespace(
        id="q3",
        name="First 5K",
        completion_type="one_time",
        skill=_make_skill("Cardio Running"),
        template=SimpleNamespace(
            parameters='{"keywords":["5K","5 km"],"activity":"running"}'
        ),
    )
    entry = _make_entry(
        datetime(2026, 2, 22, tzinfo=timezone.utc), "I completed my first 5k run today"
    )

    assert check_quest_match(quest, entry, ["Cardio Running"], ["running"]) is True
    assert check_quest_match(quest, entry, ["Cardio Running"], ["walking"]) is False


def test_one_time_malformed_criteria_fails_closed() -> None:
    quest = SimpleNamespace(
        id="q4",
        name="Bad Criteria",
        completion_type="one_time",
        skill=_make_skill("Python Programming"),
        template=SimpleNamespace(parameters='{"keywords": ['),
    )
    entry = _make_entry(datetime(2026, 2, 22, tzinfo=timezone.utc), "coded all day")

    assert check_quest_match(quest, entry, ["Python Programming"], ["coded"]) is False


def test_recursive_respects_progress_cap_and_same_day_dedupe() -> None:
    quest_done = SimpleNamespace(
        id="q5",
        name="Meditate Weekly",
        completion_type="recursive",
        skill=_make_skill("Meditation"),
        current_progress=3,
        required_progress=3,
        updated_at_utc_ms=None,
        created_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    quest_same_day = SimpleNamespace(
        id="q6",
        name="Meditate Weekly",
        completion_type="recursive",
        skill=_make_skill("Meditation"),
        current_progress=1,
        required_progress=3,
        updated_at_utc_ms=int(
            datetime(2026, 2, 22, 8, tzinfo=timezone.utc).timestamp() * 1000
        ),
        created_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    entry = _make_entry(datetime(2026, 2, 22, 18, tzinfo=timezone.utc))

    assert check_quest_match(quest_done, entry, ["Meditation"], ["meditated"]) is False
    assert (
        check_quest_match(quest_same_day, entry, ["Meditation"], ["meditated"]) is False
    )


def test_update_progress_ignores_non_positive_delta() -> None:
    quest = SimpleNamespace(
        id="q7",
        status="active",
        current_progress=10,
        required_progress=20,
        completed_at=None,
        completed_at_utc_ms=None,
    )
    db = SimpleNamespace(flush=MagicMock())

    completed = update_quest_progress(quest, 0, db)
    assert completed is False
    assert quest.current_progress == 10

    completed = update_quest_progress(quest, -5, db)
    assert completed is False
    assert quest.current_progress == 10


def test_update_progress_completion_transition_sets_fields() -> None:
    quest = SimpleNamespace(
        id="q8",
        status="active",
        current_progress=0,
        required_progress=2,
        completed_at=None,
        completed_at_utc_ms=None,
    )
    db = SimpleNamespace(flush=MagicMock())

    completed = update_quest_progress(quest, 2, db)
    assert completed is True
    assert quest.status == "completed"
    assert quest.completed_at is not None
    assert isinstance(quest.completed_at_utc_ms, int)
