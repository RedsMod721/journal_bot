from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.api.routes.users import UserCreate, create_user
from src.db.base import Base
from src.db.models.story import ArcTrigger, StoryArc
from src.db.models.user import User


def _make_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return session_local()


def test_create_user_creates_active_tutorial_arc() -> None:
    with _make_db() as db:
        payload = UserCreate(
            email="new-user@example.com",
            password="supersecret",
            username="new_user",
            timezone="UTC",
            home_country="US",
        )

        created = create_user(payload=payload, db=db)

        user = db.query(User).filter(User.id == created.id).one()
        tutorial_arc = (
            db.query(StoryArc)
            .filter(StoryArc.user_id == user.id, StoryArc.arc_type == "tutorial")
            .one()
        )
        signup_trigger = (
            db.query(ArcTrigger)
            .filter(
                ArcTrigger.user_id == user.id,
                ArcTrigger.arc_id == tutorial_arc.id,
                ArcTrigger.trigger_type == "signup",
            )
            .one()
        )

        assert tutorial_arc.status == "active"
        assert user.active_arc_id == tutorial_arc.id
        assert signup_trigger.triggered_at
