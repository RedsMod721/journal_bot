from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.core.harmony_refresh_service import HarmonyRefreshService
from src.core.harmony_scoring_service import HarmonyScoringService
from src.db.base import Base
from src.db.models.forgiveness import ForgivenessConfig
from src.db.models.harmony import HarmonyDimension
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.user import User


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


def _create_user(db: Session, *, user_id: str = "u-harmony", timezone_name: str = "Europe/Paris") -> User:
    user = User(
        id=user_id,
        username=f"user-{user_id}",
        email=f"{user_id}@example.com",
        password_hash="hash",
        timezone=timezone_name,
        home_country="US",
    )
    db.add(user)
    db.commit()
    return user


def _create_balanced_config(db: Session, user: User, preset: str = "balanced") -> None:
    config = ForgivenessConfig(
        user_id=user.id,
        preset=preset,
        skill_decay_rate=0.05,
        insight_decay_rate=0.10,
        skill_grace_period_days=7,
        insight_grace_period_days=3,
        critical_staleness_threshold=0.80,
    )
    db.add(config)
    db.flush()
    user.forgiveness_config_id = config.id
    db.commit()


def _add_entry(
    db: Session,
    user_id: str,
    *,
    created_at: datetime,
    content: str,
    task_type: str,
    energy_level: int | None = None,
) -> None:
    entry = JournalEntry(
        user_id=user_id,
        content=content,
        entry_type="text",
        status="completed",
        created_at=created_at,
    )
    db.add(entry)
    db.flush()
    db.add(
        JournalEntryStructured(
            user_id=user_id,
            entry_id=entry.id,
            canonical_text=content,
            task_type=task_type,
            energy_level=energy_level,
        )
    )
    db.commit()


def test_read_only_refresh_does_not_mutate_overwork_persistence(db_session: Session) -> None:
    user = _create_user(db_session)
    _create_balanced_config(db_session, user)
    now = datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)
    for offset in range(5):
        _add_entry(
            db_session,
            user.id,
            created_at=now - timedelta(days=offset + 1),
            content="Work project sprint",
            task_type="administrative",
            energy_level=3,
        )

    service = HarmonyRefreshService(db_session)
    result = service.refresh_harmony(user.id, now, advance_overwork_state=False)

    assert result.overwork.condition is True
    assert result.overwork.stage == 0
    assert result.harmony.overwork_stage == 0
    assert result.harmony.overwork_consecutive_days == 0
    assert result.harmony.overwork_last_evaluated_local_date is None


def test_advance_overwork_uses_balanced_thresholds_and_deescalates(
    db_session: Session,
) -> None:
    user = _create_user(db_session)
    _create_balanced_config(db_session, user)
    harmony = HarmonyDimension(
        user_id=user.id,
        physical=0.50,
        mental=0.80,
        social=0.80,
        productivity=0.90,
        rest=0.25,
        growth=0.80,
        creative=0.80,
        overall_balance=0.6642857,
    )
    db_session.add(harmony)
    db_session.commit()

    service = HarmonyScoringService(db_session)

    day_1 = service.advance_overwork_state(
        harmony,
        user_id=user.id,
        today_local=datetime(2026, 3, 10).date(),
        now_utc=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
        average_energy=4.0,
    )
    day_2 = service.advance_overwork_state(
        harmony,
        user_id=user.id,
        today_local=datetime(2026, 3, 11).date(),
        now_utc=datetime(2026, 3, 11, 10, 0, tzinfo=timezone.utc),
        average_energy=4.0,
    )
    day_3 = service.advance_overwork_state(
        harmony,
        user_id=user.id,
        today_local=datetime(2026, 3, 12).date(),
        now_utc=datetime(2026, 3, 12, 10, 0, tzinfo=timezone.utc),
        average_energy=4.0,
    )
    day_4 = service.advance_overwork_state(
        harmony,
        user_id=user.id,
        today_local=datetime(2026, 3, 13).date(),
        now_utc=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
        average_energy=4.0,
    )

    assert day_1.stage == 0
    assert day_2.stage == 1
    assert day_3.stage == 1
    assert day_4.stage == 2

    harmony.productivity = 0.40
    harmony.rest = 0.80
    recovery = service.advance_overwork_state(
        harmony,
        user_id=user.id,
        today_local=datetime(2026, 3, 14).date(),
        now_utc=datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc),
        average_energy=7.0,
    )
    assert recovery.condition is False
    assert recovery.consecutive_days == 3
    assert recovery.stage == 1


def test_refresh_harmony_uses_user_timezone_for_snapshot_day(db_session: Session) -> None:
    user = _create_user(db_session, timezone_name="Europe/Paris")
    _create_balanced_config(db_session, user)
    service = HarmonyRefreshService(db_session)

    result = service.refresh_harmony(
        user.id,
        datetime(2026, 3, 11, 23, 30, tzinfo=timezone.utc),
        advance_overwork_state=False,
    )

    assert result.snapshot_date_local.isoformat() == "2026-03-11"
