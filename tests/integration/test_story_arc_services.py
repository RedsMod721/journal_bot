from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.core.arc_lifecycle import ArcLifecycleService
from src.core.arc_recovery_detection import RecoveryDetectionService
from src.core.arc_regression_trigger import RegressionTriggerService
from src.db.base import Base
from src.db.models.skill import Skill
from src.db.models.story import ArcTrigger, StoryArc
from src.db.models.user import User

pytestmark = [pytest.mark.integration]


def _fixed_ms(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:23] + "Z"


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    LocalSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = LocalSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def test_user(db_session: Session) -> User:
    user = User(
        id="00000000-0000-0000-0000-000000001000",
        username="story_arc_user",
        email="story-arc@example.com",
        password_hash="x",
        home_country="US",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _add_skills(db_session: Session, user_id: str, staleness_values: list[float]) -> None:
    for idx, staleness in enumerate(staleness_values, start=1):
        db_session.add(
            Skill(
                id=f"00000000-0000-0000-0000-0000000011{idx:02d}",
                user_id=user_id,
                name=f"Skill {idx}",
                canonical_name=f"skill_{idx}",
                staleness=staleness,
                xp=0,
                level=1,
                rank="F",
            )
        )
    db_session.commit()


def test_regression_trigger_creates_arc_for_stale_skills(
    db_session: Session,
    test_user: User,
) -> None:
    _add_skills(db_session, test_user.id, [0.8, 0.7, 0.65, 0.45])

    service = RegressionTriggerService(db_session)
    arc = service.check_and_trigger_regression(test_user.id)

    triggers = (
        db_session.query(ArcTrigger)
        .filter(ArcTrigger.arc_id == arc.id)
        .order_by(ArcTrigger.trigger_type.asc())
        .all()
    )

    assert arc is not None
    assert arc.arc_type == "regression"
    assert arc.status == "active"
    assert {trigger.trigger_type for trigger in triggers} == {
        "regression_baseline",
        "skill_decay",
    }


def test_active_event_defers_regression(
    db_session: Session,
    test_user: User,
) -> None:
    _add_skills(db_session, test_user.id, [0.9, 0.8, 0.7, 0.6])
    lifecycle = ArcLifecycleService(db_session)
    event_arc = lifecycle.create_arc(
        user_id=test_user.id,
        arc_type="event",
        event_name="exam_week",
        make_active=True,
    )
    db_session.commit()

    service = RegressionTriggerService(db_session)
    arc = service.check_and_trigger_regression(test_user.id)
    deferred = (
        db_session.query(ArcTrigger)
        .filter(
            ArcTrigger.arc_id == event_arc.id,
            ArcTrigger.trigger_type == "regression_deferred",
        )
        .one()
    )

    assert arc is None
    assert deferred.trigger_data is not None


def test_vacation_suppresses_regression(
    db_session: Session,
    test_user: User,
) -> None:
    _add_skills(db_session, test_user.id, [0.9, 0.8, 0.7, 0.6])
    lifecycle = ArcLifecycleService(db_session)
    vacation_arc = lifecycle.create_arc(
        user_id=test_user.id,
        arc_type="event",
        event_name="vacation_mode",
        decay_rate_multiplier_bp=0,
        make_active=True,
    )
    db_session.commit()

    service = RegressionTriggerService(db_session)
    arc = service.check_and_trigger_regression(test_user.id)
    suppressed = (
        db_session.query(ArcTrigger)
        .filter(
            ArcTrigger.arc_id == vacation_arc.id,
            ArcTrigger.trigger_type == "regression_suppressed",
        )
        .one()
    )

    assert arc is None
    assert suppressed.trigger_data is not None


def test_recovery_transition_creates_redemption(
    db_session: Session,
    test_user: User,
) -> None:
    _add_skills(db_session, test_user.id, [0.2, 0.18, 0.15, 0.12])
    lifecycle = ArcLifecycleService(db_session)
    regression_arc = lifecycle.create_arc(
        user_id=test_user.id,
        arc_type="regression",
        make_active=True,
    )
    regression_arc.started_at = _fixed_ms(datetime.now(timezone.utc) - timedelta(days=8))
    regression_arc.updated_at = regression_arc.started_at
    lifecycle._write_trigger(
        arc_id=regression_arc.id,
        user_id=test_user.id,
        trigger_type="regression_baseline",
        trigger_data={
            "avg_staleness_at_trigger": 0.65,
            "eligible_skill_count": 4,
            "high_staleness_count": 3,
            "source": "skill_decay",
        },
        now=regression_arc.started_at,
    )
    db_session.commit()

    service = RecoveryDetectionService(db_session)
    redemption_arc = service.check_and_transition_to_redemption(test_user.id)

    db_session.refresh(regression_arc)
    recovery_trigger = (
        db_session.query(ArcTrigger)
        .filter(
            ArcTrigger.arc_id == redemption_arc.id,
            ArcTrigger.trigger_type == "recovery_detected",
        )
        .one()
    )

    assert redemption_arc is not None
    assert regression_arc.status == "completed"
    assert redemption_arc.arc_type == "redemption"
    assert redemption_arc.status == "active"
    assert json.loads(recovery_trigger.trigger_data)["regression_arc_id"] == regression_arc.id
