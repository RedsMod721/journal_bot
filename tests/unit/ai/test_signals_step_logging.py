from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.ai.steps import signals
from src.db.base import Base
from src.db.models.user import User


def _make_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return local()


def test_signals_detect_pushups_as_physical_activity(caplog) -> None:
    with _make_db() as db:
        user = User(
            id="00000000-0000-0000-0000-000000009001",
            email="signals-log@example.com",
            password_hash="x",
            home_country="US",
        )
        db.add(user)
        db.commit()

        caplog.set_level(logging.INFO)

        result = signals.run(
            user_id=user.id,
            canonical_text="I did a 50 pushup session",
            db=db,
        )

        assert result["detected_skills"] == []
        assert "pushup" in result["detected_activities"]
        assert result["task_type"] == "physical"
        assert "[pipeline:signals]" in caplog.text
        assert "pushup" in caplog.text
        assert "without user skill matches" in caplog.text
