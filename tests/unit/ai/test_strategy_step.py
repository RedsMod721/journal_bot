"""Branch tests for src.ai.steps.strategy helpers."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import src.ai.steps.strategy as strategy


class _FakeQuery:
    def __init__(self, *, first_row=None, one_row=None) -> None:
        self._first_row = first_row
        self._one_row = one_row

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._first_row

    def one_or_none(self):
        return self._one_row


class _FakeDB:
    def __init__(self, *, first_row=None, one_row=None) -> None:
        self.first_row = first_row
        self.one_row = one_row
        self.added: list[object] = []

    def query(self, _model):
        return _FakeQuery(first_row=self.first_row, one_row=self.one_row)

    def add(self, obj: object) -> None:
        self.added.append(obj)


def test_diminishing_multiplier_handles_bad_json_and_bad_count() -> None:
    yesterday = date(2026, 3, 8)
    assert (
        strategy.diminishing_multiplier_from_streaks(["study"], "{bad", yesterday)
        == 1.0
    )

    streaks = json.dumps(
        {"study": {"last_day": yesterday.isoformat(), "count": "oops"}}
    )
    assert (
        strategy.diminishing_multiplier_from_streaks(["study"], streaks, yesterday)
        == 1.0
    )


def test_update_strategy_streaks_updates_today_yesterday_and_new() -> None:
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    row = SimpleNamespace(
        strategy_streaks_json=json.dumps(
            {
                "social": {"count": 3, "last_day": today.isoformat()},
                "study": {"count": 2, "last_day": yesterday.isoformat()},
            }
        )
    )
    db = _FakeDB(first_row=row)

    strategy._update_strategy_streaks(  # noqa: SLF001 - testing internal helper
        user_id="u1",
        credited_strategies=["social", "study", "mundane"],
        db=db,
    )

    out = json.loads(row.strategy_streaks_json)
    assert out["social"]["count"] == 3
    assert out["study"]["count"] == 3
    assert out["mundane"]["count"] == 1
    assert out["study"]["last_day"] == today.isoformat()


def test_increment_strategy_count_upsert_and_increment() -> None:
    # CREATE path: no existing row → new StrategyTracking added with column set to 1
    create_db = _FakeDB(one_row=None)
    strategy._increment_strategy_count(  # noqa: SLF001 - testing internal helper
        user_id="u1",
        strategy_name="social",
        db=create_db,
    )
    assert len(create_db.added) == 1
    assert create_db.added[0].social_risk_count == 1

    # UPDATE path: existing row → named column incremented
    row = SimpleNamespace(study_burst_count=4, updated_at=None)
    update_db = _FakeDB(one_row=row)
    strategy._increment_strategy_count(  # noqa: SLF001 - testing internal helper
        user_id="u1",
        strategy_name="study",
        db=update_db,
    )
    assert row.study_burst_count == 5
    assert row.updated_at is not None


def test_increment_strategy_count_unknown_strategy_is_noop() -> None:
    # Unknown strategy names must not raise or add rows (architecture §5.0.3).
    db = _FakeDB(one_row=None)
    strategy._increment_strategy_count(  # noqa: SLF001 - testing internal helper
        user_id="u1",
        strategy_name="nonexistent",
        db=db,
    )
    assert len(db.added) == 0
