"""Tests for the vacation mode service (Section 8.3.5 and 8.5.4)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401 — registers all mappers with Base
from src.core.arc_lifecycle import ArcLifecycleService
from src.core.arc_timestamps import now_utc_fixed_ms, parse_fixed_ms_timestamp
from src.core.arc_vacation import VacationModeService
from src.db.base import Base
from src.db.models.story import ArcTrigger, StoryArc
from src.db.models.user import User


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
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


@pytest.fixture
def test_user(db_session: Session) -> User:
    user = User(
        email="vacation_test@example.com",
        password_hash="hash",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #


def _get_triggers(db: Session, arc_id: str, trigger_type: str) -> list[ArcTrigger]:
    return (
        db.query(ArcTrigger)
        .filter(ArcTrigger.arc_id == arc_id, ArcTrigger.trigger_type == trigger_type)
        .all()
    )


# ------------------------------------------------------------------ #
# activate_vacation                                                   #
# ------------------------------------------------------------------ #


def test_activate_vacation_no_prior_arc(db_session: Session, test_user: User) -> None:
    """Vacation with no prior active arc creates a vacation arc, pauses nothing."""
    svc = VacationModeService(db_session)

    vacation_arc, paused_arc = svc.activate_vacation(
        user_id=test_user.id,
        duration_days=7,
    )

    assert vacation_arc.arc_type == "event"
    assert vacation_arc.event_name == "vacation_mode"
    assert vacation_arc.status == "active"
    assert vacation_arc.decay_rate_multiplier_bp == 0  # Section 8.3.5: no decay

    assert paused_arc is None

    # No vacation_pause trigger should be on the vacation arc (nothing to record)
    pause_triggers = _get_triggers(db_session, vacation_arc.id, "vacation_pause")
    assert pause_triggers == []


def test_activate_vacation_pauses_current_arc(db_session: Session, test_user: User) -> None:
    """Vacation pauses the current active arc and becomes the new active arc."""
    lifecycle = ArcLifecycleService(db_session)
    svc = VacationModeService(db_session)

    event_arc = lifecycle.create_arc(
        user_id=test_user.id,
        arc_type="event",
        event_name="exam_week",
        duration_days=7,
        make_active=True,
    )
    original_started_at = event_arc.started_at

    vacation_arc, paused_arc = svc.activate_vacation(
        user_id=test_user.id,
        duration_days=14,
    )

    # Vacation arc is active
    assert vacation_arc.event_name == "vacation_mode"
    assert vacation_arc.status == "active"
    assert vacation_arc.decay_rate_multiplier_bp == 0

    # Previous arc is paused
    assert paused_arc is not None
    assert paused_arc.id == event_arc.id
    assert paused_arc.status == "paused"

    # started_at of the paused arc must not change (Section 8.5.4 immutability)
    assert paused_arc.started_at == original_started_at

    # Only the vacation arc should be active
    active = lifecycle.get_active_arc(test_user.id)
    assert active is not None
    assert active.id == vacation_arc.id

    # vacation_pause trigger on the vacation arc records the paused arc id
    pause_triggers = _get_triggers(db_session, vacation_arc.id, "vacation_pause")
    assert len(pause_triggers) == 1
    data = json.loads(pause_triggers[0].trigger_data)
    assert data["paused_arc_id"] == event_arc.id
    assert data["paused_arc_type"] == "event"

    # vacation_pause trigger on the paused arc (written by _pause_arc for days_active)
    paused_arc_pause_triggers = _get_triggers(db_session, event_arc.id, "vacation_pause")
    assert len(paused_arc_pause_triggers) == 1


def test_activate_vacation_idempotent_if_already_in_vacation(
    db_session: Session, test_user: User
) -> None:
    """Calling activate_vacation while in vacation mode returns existing arc."""
    svc = VacationModeService(db_session)

    vacation_arc, _ = svc.activate_vacation(user_id=test_user.id)
    same_arc, paused = svc.activate_vacation(user_id=test_user.id)

    assert same_arc.id == vacation_arc.id
    assert paused is None


def test_activate_vacation_sets_zero_decay(db_session: Session, test_user: User) -> None:
    """Decay rate multiplier is always 0 regardless of caller arguments."""
    svc = VacationModeService(db_session)

    vacation_arc, _ = svc.activate_vacation(user_id=test_user.id)

    assert vacation_arc.decay_rate_multiplier_bp == 0
    assert vacation_arc.decay_rate_multiplier == 0.0


# ------------------------------------------------------------------ #
# end_vacation                                                        #
# ------------------------------------------------------------------ #


def test_end_vacation_no_resume(db_session: Session, test_user: User) -> None:
    """Ending a vacation with no paused arc completes the vacation, resumes nothing."""
    lifecycle = ArcLifecycleService(db_session)
    svc = VacationModeService(db_session)

    svc.activate_vacation(user_id=test_user.id, duration_days=7)
    ended_vacation, resumed_arc = svc.end_vacation(test_user.id)

    assert ended_vacation.status == "completed"
    assert ended_vacation.completed_at is not None
    assert resumed_arc is None

    # No active arc afterward
    assert lifecycle.get_active_arc(test_user.id) is None


def test_end_vacation_resumes_paused_arc(db_session: Session, test_user: User) -> None:
    """Ending vacation resumes the previously paused arc with started_at unchanged."""
    lifecycle = ArcLifecycleService(db_session)
    svc = VacationModeService(db_session)

    event_arc = lifecycle.create_arc(
        user_id=test_user.id,
        arc_type="event",
        event_name="project_sprint",
        make_active=True,
    )
    original_started_at = event_arc.started_at

    svc.activate_vacation(user_id=test_user.id)
    ended_vacation, resumed_arc = svc.end_vacation(test_user.id)

    # Vacation completed
    assert ended_vacation.status == "completed"

    # Paused arc is now active again
    assert resumed_arc is not None
    assert resumed_arc.id == event_arc.id
    assert resumed_arc.status == "active"

    # CRITICAL: started_at must never change (Section 8.5.4)
    assert resumed_arc.started_at == original_started_at

    # Resumed arc is now the active arc
    active = lifecycle.get_active_arc(test_user.id)
    assert active is not None
    assert active.id == event_arc.id

    # vacation_resume trigger written on the resumed arc
    resume_triggers = _get_triggers(db_session, event_arc.id, "vacation_resume")
    assert len(resume_triggers) == 1

    # user_end trigger on the vacation arc
    end_triggers = _get_triggers(db_session, ended_vacation.id, "user_end")
    assert len(end_triggers) == 1


def test_end_vacation_raises_if_not_in_vacation(
    db_session: Session, test_user: User
) -> None:
    """end_vacation raises ValueError when no vacation arc is active."""
    svc = VacationModeService(db_session)

    with pytest.raises(ValueError, match="No active vacation mode"):
        svc.end_vacation(test_user.id)


def test_end_vacation_raises_if_different_arc_active(
    db_session: Session, test_user: User
) -> None:
    """end_vacation raises if a non-vacation arc is active."""
    lifecycle = ArcLifecycleService(db_session)
    svc = VacationModeService(db_session)

    lifecycle.create_arc(
        user_id=test_user.id,
        arc_type="event",
        event_name="exam_week",
        make_active=True,
    )

    with pytest.raises(ValueError, match="No active vacation mode"):
        svc.end_vacation(test_user.id)


# ------------------------------------------------------------------ #
# days_active excludes paused duration (Section 8.5.4)              #
# ------------------------------------------------------------------ #


def test_vacation_days_active_excludes_paused_time(
    db_session: Session, test_user: User
) -> None:
    """calculate_days_active on a resumed arc subtracts the vacation pause duration.

    Strategy: activate and end vacation, then back-date the pause/resume trigger
    timestamps to simulate 7 days of vacation after 3 days of activity.
    At t=10d the resumed arc should report ~3 days active, not ~10.
    """
    lifecycle = ArcLifecycleService(db_session)
    svc = VacationModeService(db_session)

    event_arc = lifecycle.create_arc(
        user_id=test_user.id,
        arc_type="event",
        event_name="learning_challenge",
        make_active=True,
    )

    event_started = parse_fixed_ms_timestamp(event_arc.started_at)

    # Activate and immediately end vacation (triggers written with now()).
    svc.activate_vacation(user_id=test_user.id)
    _, resumed_arc = svc.end_vacation(test_user.id)

    assert resumed_arc is not None

    # Backdate the vacation_pause trigger on the paused arc to day 3.
    def _fmt(dt: datetime) -> str:
        ms = dt.microsecond // 1000
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{ms:03d}Z"

    day3 = event_started + timedelta(days=3)
    day10 = event_started + timedelta(days=10)

    pause_trigger = (
        db_session.query(ArcTrigger)
        .filter(
            ArcTrigger.arc_id == event_arc.id,
            ArcTrigger.trigger_type == "vacation_pause",
        )
        .one()
    )
    resume_trigger = (
        db_session.query(ArcTrigger)
        .filter(
            ArcTrigger.arc_id == event_arc.id,
            ArcTrigger.trigger_type == "vacation_resume",
        )
        .one()
    )

    pause_trigger.triggered_at = _fmt(day3)
    resume_trigger.triggered_at = _fmt(day10)
    db_session.commit()

    # Evaluate days_active at day 10: elapsed=10d, paused=7d → active=3d
    days = lifecycle.calculate_days_active(
        db_session.get(StoryArc, event_arc.id),
        now_utc=day10,
    )
    assert abs(days - 3.0) < 0.01


# ------------------------------------------------------------------ #
# get_vacation_status                                                 #
# ------------------------------------------------------------------ #


def test_get_vacation_status_not_in_vacation(
    db_session: Session, test_user: User
) -> None:
    svc = VacationModeService(db_session)

    status = svc.get_vacation_status(test_user.id)

    assert status["in_vacation"] is False
    assert status["vacation_arc"] is None
    assert status["paused_arc"] is None
    assert status["days_active"] is None


def test_get_vacation_status_in_vacation(db_session: Session, test_user: User) -> None:
    lifecycle = ArcLifecycleService(db_session)
    svc = VacationModeService(db_session)

    prior_arc = lifecycle.create_arc(
        user_id=test_user.id,
        arc_type="event",
        event_name="side_project",
        make_active=True,
    )

    vacation_arc, _ = svc.activate_vacation(user_id=test_user.id)
    status = svc.get_vacation_status(test_user.id)

    assert status["in_vacation"] is True
    assert status["vacation_arc"].id == vacation_arc.id
    assert status["paused_arc"] is not None
    assert status["paused_arc"].id == prior_arc.id
    assert isinstance(status["days_active"], float)
    assert status["days_active"] >= 0.0


def test_get_vacation_status_after_end(db_session: Session, test_user: User) -> None:
    svc = VacationModeService(db_session)

    svc.activate_vacation(user_id=test_user.id)
    svc.end_vacation(test_user.id)

    status = svc.get_vacation_status(test_user.id)
    assert status["in_vacation"] is False


# ------------------------------------------------------------------ #
# Full round-trip                                                     #
# ------------------------------------------------------------------ #


def test_full_vacation_round_trip(db_session: Session, test_user: User) -> None:
    """Full activate → end → resume round trip with all invariants checked."""
    lifecycle = ArcLifecycleService(db_session)
    svc = VacationModeService(db_session)

    # Setup: one active arc.
    event_arc = lifecycle.create_arc(
        user_id=test_user.id,
        arc_type="event",
        event_name="hackathon",
        make_active=True,
    )
    arc_started_at = event_arc.started_at

    # Activate.
    vacation_arc, paused_arc = svc.activate_vacation(user_id=test_user.id, duration_days=5)

    assert vacation_arc.status == "active"
    assert paused_arc is not None and paused_arc.status == "paused"
    assert lifecycle.get_active_arc(test_user.id).id == vacation_arc.id

    # Vacation status reflects reality.
    vs = svc.get_vacation_status(test_user.id)
    assert vs["in_vacation"] is True
    assert vs["paused_arc"].id == event_arc.id

    # End.
    ended, resumed = svc.end_vacation(test_user.id)

    assert ended.status == "completed"
    assert resumed is not None and resumed.status == "active"
    assert resumed.started_at == arc_started_at  # immutability

    # Triggers audit trail.
    assert len(_get_triggers(db_session, vacation_arc.id, "vacation_pause")) == 1
    assert len(_get_triggers(db_session, vacation_arc.id, "user_end")) == 1
    assert len(_get_triggers(db_session, event_arc.id, "vacation_pause")) == 1
    assert len(_get_triggers(db_session, event_arc.id, "vacation_resume")) == 1
