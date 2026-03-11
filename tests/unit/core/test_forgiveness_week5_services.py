from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.core.forgiveness_decay_service import ForgivenessDecayService
from src.db.base import Base
from src.db.models.forgiveness import ForgivenessConfig
from src.db.models.skill import Skill
from src.db.models.story import StoryArc
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


def _create_user(db: Session, *, user_id: str = "u-forgive", timezone_name: str = "Europe/Paris") -> User:
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


def _attach_balanced_config(db: Session, user: User) -> None:
    config = ForgivenessConfig(
        user_id=user.id,
        preset="balanced",
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


def _create_skill(db: Session, user_id: str) -> Skill:
    skill = Skill(
        user_id=user_id,
        name="Programming",
        canonical_name="programming",
        staleness=0.0,
        last_activity_at=datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
    )
    db.add(skill)
    db.commit()
    return skill


def test_decay_consumes_active_arc_multiplier(db_session: Session) -> None:
    user = _create_user(db_session)
    _attach_balanced_config(db_session, user)
    skill = _create_skill(db_session, user.id)
    service = ForgivenessDecayService(db_session)
    now = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)

    no_arc = service.decay_skills(user.id, now)
    db_session.refresh(skill)
    baseline_staleness = skill.staleness
    assert no_arc["skills_decayed"] == 1

    skill.staleness = 0.0
    db_session.add(
        StoryArc(
            user_id=user.id,
            status="active",
            arc_type="event",
            title="Vacation",
            decay_rate_multiplier=0.25,
        )
    )
    db_session.flush()
    user.active_arc_id = (
        db_session.query(StoryArc).filter(StoryArc.user_id == user.id).first().id
    )
    db_session.commit()
    service.decay_skills(user.id, now)
    db_session.refresh(skill)
    slowed_staleness = skill.staleness

    assert slowed_staleness < baseline_staleness

    skill.staleness = 0.0
    arc = db_session.query(StoryArc).filter(StoryArc.user_id == user.id).first()
    arc.decay_rate_multiplier = 0.0
    db_session.commit()
    service.decay_skills(user.id, now)
    db_session.refresh(skill)
    assert skill.staleness == 0.0


def test_resolve_snapshot_date_uses_user_timezone(db_session: Session) -> None:
    user = _create_user(db_session, timezone_name="Europe/Paris")
    _attach_balanced_config(db_session, user)
    service = ForgivenessDecayService(db_session)

    snapshot_date = service.resolve_snapshot_date(
        user.id,
        datetime(2026, 3, 11, 23, 30, tzinfo=timezone.utc),
    )

    assert snapshot_date.isoformat() == "2026-03-12"
