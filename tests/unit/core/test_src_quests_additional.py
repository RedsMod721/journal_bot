"""Additional unit tests for uncovered branches in src.core.quests."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.core import quests as quests_module
from src.core.quests import check_quest_match, match_quests, update_quest_progress


def _make_skill(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _make_entry(
    content: str = "", created_at: datetime | None = None
) -> SimpleNamespace:
    return SimpleNamespace(content=content, created_at=created_at)


def test_one_time_non_dict_criteria_fails_closed() -> None:
    quest = SimpleNamespace(
        id="q-non-dict",
        completion_type="one_time",
        skill=_make_skill("Python"),
        template=SimpleNamespace(parameters='["not-a-dict"]'),
    )
    entry = _make_entry(
        content="Worked on python",
        created_at=datetime(2026, 2, 27, tzinfo=timezone.utc),
    )

    assert check_quest_match(quest, entry, ["Python"], ["coded"]) is False


def test_one_time_without_template_falls_back_to_skill_match() -> None:
    quest = SimpleNamespace(
        id="q-no-template",
        completion_type="one_time",
        skill=_make_skill("Python"),
        template=None,
    )
    entry = _make_entry(created_at=datetime(2026, 2, 27, tzinfo=timezone.utc))

    assert check_quest_match(quest, entry, ["python"], []) is True
    assert check_quest_match(quest, entry, ["running"], []) is False


def test_cumulative_matches_only_when_skill_matches() -> None:
    quest = SimpleNamespace(
        id="q-cumulative",
        completion_type="cumulative",
        skill=_make_skill("Deep Work"),
    )
    entry = _make_entry(created_at=datetime(2026, 2, 27, tzinfo=timezone.utc))

    assert check_quest_match(quest, entry, ["deep work"], []) is True
    assert check_quest_match(quest, entry, ["cardio"], []) is False


def test_recursive_rejects_when_skill_does_not_match() -> None:
    quest = SimpleNamespace(
        id="q-recursive-no-skill",
        completion_type="recursive",
        skill=_make_skill("Meditation"),
        current_progress=0,
        required_progress=3,
        updated_at_utc_ms=None,
        created_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    entry = _make_entry(created_at=datetime(2026, 2, 27, tzinfo=timezone.utc))

    assert check_quest_match(quest, entry, ["Running"], []) is False


def test_recursive_success_on_new_day_before_cap() -> None:
    quest = SimpleNamespace(
        id="q-recursive-success",
        completion_type="recursive",
        skill=_make_skill("Meditation"),
        current_progress=1,
        required_progress=3,
        updated_at_utc_ms=int(
            datetime(2026, 2, 26, 8, tzinfo=timezone.utc).timestamp() * 1000
        ),
        created_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    entry = _make_entry(created_at=datetime(2026, 2, 27, 9, tzinfo=timezone.utc))

    assert check_quest_match(quest, entry, ["meditation"], ["meditated"]) is True


def test_streak_rejects_when_skill_does_not_match() -> None:
    quest = SimpleNamespace(
        id="q-streak-no-skill",
        completion_type="streak",
        skill=_make_skill("Running"),
        current_progress=1,
        required_progress=30,
        updated_at_utc_ms=None,
        created_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    entry = _make_entry(created_at=datetime(2026, 2, 27, tzinfo=timezone.utc))

    assert check_quest_match(quest, entry, ["Yoga"], []) is False


def test_streak_match_requires_entry_date() -> None:
    quest = SimpleNamespace(
        id="q-streak-no-date",
        completion_type="streak",
        skill=_make_skill("Running"),
        current_progress=5,
        required_progress=30,
        updated_at_utc_ms=None,
        created_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    entry = _make_entry(content="ran", created_at=None)

    assert check_quest_match(quest, entry, ["running"], ["ran"]) is False


def test_quest_last_progress_date_uses_completed_at_fallback() -> None:
    quest = SimpleNamespace(
        id="q-completed-at",
        completion_type="streak",
        skill=_make_skill("Running"),
        current_progress=1,
        required_progress=30,
        updated_at_utc_ms=None,
        completed_at=datetime(2026, 2, 26, tzinfo=timezone.utc),
        created_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    entry = _make_entry(created_at=datetime(2026, 2, 27, tzinfo=timezone.utc))

    assert check_quest_match(quest, entry, ["running"], ["ran"]) is True


def test_skill_name_errors_fail_closed() -> None:
    class _BadQuest:
        completion_type = "cumulative"

        @property
        def skill(self):  # noqa: ANN201
            raise RuntimeError("broken relationship")

    entry = _make_entry(created_at=datetime(2026, 2, 27, tzinfo=timezone.utc))
    assert check_quest_match(_BadQuest(), entry, ["anything"], []) is False


def test_match_quests_filters_and_skips_check_exceptions() -> None:
    q1 = SimpleNamespace(id="q1")
    q2 = SimpleNamespace(id="q2")
    query = MagicMock()
    query.filter.return_value = query
    query.options.return_value = query
    query.all.return_value = [q1, q2]
    db = MagicMock()
    db.query.return_value = query
    entry = _make_entry(created_at=datetime(2026, 2, 27, tzinfo=timezone.utc))

    with patch.object(
        quests_module, "check_quest_match", side_effect=[True, RuntimeError("boom")]
    ):
        matched = match_quests(entry, "user-1", ["python"], ["coded"], db)

    assert matched == [q1]


def test_streak_break_marks_failed_on_gap_gt_one_day() -> None:
    quest = SimpleNamespace(
        id="q-streak-break",
        name="Run Daily",
        status="active",
        completion_type="streak",
        skill=_make_skill("Running"),
        current_progress=3,
        required_progress=30,
        updated_at_utc_ms=int(
            datetime(2026, 2, 24, 8, tzinfo=timezone.utc).timestamp() * 1000
        ),
        created_at=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )
    entry = _make_entry(created_at=datetime(2026, 2, 27, 8, tzinfo=timezone.utc))

    assert check_quest_match(quest, entry, ["running"], ["ran"]) is False
    assert quest.status == "failed"


def test_unknown_completion_type_fails_closed() -> None:
    quest = SimpleNamespace(
        id="q-unknown",
        completion_type="mystery_mode",
        skill=_make_skill("Any"),
    )
    entry = _make_entry(created_at=datetime(2026, 2, 27, tzinfo=timezone.utc))

    assert check_quest_match(quest, entry, ["Any"], []) is False


def test_update_progress_noop_when_already_completed() -> None:
    quest = SimpleNamespace(
        id="q-complete",
        status="completed",
        current_progress=10,
        required_progress=10,
        completed_at=datetime(2026, 2, 26, tzinfo=timezone.utc),
        completed_at_utc_ms=1700000000000,
    )
    db = SimpleNamespace(flush=MagicMock())

    completed = update_quest_progress(quest, 5, db)

    assert completed is False
    db.flush.assert_called_once()
