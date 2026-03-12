from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.db.base import Base
from src.db.models.forgiveness import DecaySnapshot
from src.db.models.harmony import HarmonySnapshot
from src.db.models.strategy import StrategyTracking
from src.db.models.user import User
from src.jobs.daily_decay_job import DailyDecayJob


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _create_user(db: Session, *, user_id: str, timezone_name: str) -> User:
    user = User(
        id=user_id,
        username=user_id,
        email=f"{user_id}@example.com",
        password_hash="hash",
        timezone=timezone_name,
        home_country="US",
    )
    db.add(user)
    db.commit()
    return user


def _mark_completed_for_local_day(
    db: Session,
    *,
    user_id: str,
    today_local: date,
    yesterday_local: date,
) -> None:
    db.add(
        DecaySnapshot(
            user_id=user_id,
            snapshot_date=today_local.isoformat(),
            average_skill_staleness=0.0,
            average_insight_staleness=0.0,
            skills_near_critical=0,
        )
    )
    db.add(
        HarmonySnapshot(
            user_id=user_id,
            snapshot_date=yesterday_local,
            physical=0.5,
            mental=0.5,
            social=0.5,
            productivity=0.5,
            rest=0.5,
            growth=0.5,
            creative=0.5,
            overall_balance=0.5,
        )
    )
    db.add(
        StrategyTracking(
            user_id=user_id,
            window_start_date=today_local,
            window_end_date=today_local,
        )
    )
    db.commit()


def test_due_status_skips_before_local_cutoff(db_session: Session) -> None:
    user = _create_user(db_session, user_id="u-before-cutoff", timezone_name="UTC")
    job = DailyDecayJob(db_session)

    due, reason, today_local = job._due_status_for_user(
        user,
        datetime(2026, 3, 12, 0, 10, tzinfo=timezone.utc),
    )

    assert due is False
    assert reason == "before_local_cutoff"
    assert today_local.isoformat() == "2026-03-12"


def test_due_status_skips_when_local_day_already_completed(db_session: Session) -> None:
    user = _create_user(db_session, user_id="u-complete", timezone_name="UTC")
    _mark_completed_for_local_day(
        db_session,
        user_id=user.id,
        today_local=date(2026, 3, 12),
        yesterday_local=date(2026, 3, 11),
    )
    job = DailyDecayJob(db_session)

    due, reason, _ = job._due_status_for_user(
        user,
        datetime(2026, 3, 12, 0, 30, tzinfo=timezone.utc),
    )

    assert due is False
    assert reason == "already_completed_for_local_day"


@pytest.mark.asyncio
async def test_run_for_due_users_only_executes_due_users(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    due_user = _create_user(db_session, user_id="u-due", timezone_name="UTC")
    skipped_user = _create_user(db_session, user_id="u-skipped", timezone_name="UTC")
    _mark_completed_for_local_day(
        db_session,
        user_id=skipped_user.id,
        today_local=date(2026, 3, 12),
        yesterday_local=date(2026, 3, 11),
    )

    job = DailyDecayJob(db_session)
    called: list[str] = []

    async def fake_run_for_user(user_id: str, now_utc: datetime | None = None):
        called.append(user_id)
        return {"user_id": user_id}

    monkeypatch.setattr(job, "run_for_user", fake_run_for_user)

    summary = await job.run_for_due_users(
        datetime(2026, 3, 12, 0, 30, tzinfo=timezone.utc)
    )

    assert called == [due_user.id]
    assert summary["eligible"] == 1
    assert summary["successful"] == 1
    assert summary["skipped"] == 1
