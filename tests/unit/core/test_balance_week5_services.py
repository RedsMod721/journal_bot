from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401
from src.core.balance_diminishing_returns import DiminishingReturnsService
from src.core.balance_strategy_detector import StrategyDetector
from src.core.balance_variety_service import VarietyService
from src.core.balance_window_service import BalanceWindowService
from src.core.themes import ensure_user_themes
from src.db.base import Base
from src.db.models.harmony import HarmonyDimension
from src.db.models.journal_entry import JournalEntry
from src.db.models.strategy import StrategyTracking
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


def _create_user(db: Session, user_id: str = "u-balance") -> User:
    user = User(
        id=user_id,
        username=f"user-{user_id}",
        email=f"{user_id}@example.com",
        password_hash="hash",
        timezone="Europe/Paris",
        home_country="US",
    )
    db.add(user)
    db.commit()
    return user


def test_variety_bonus_caps_at_thirty_percent(db_session: Session) -> None:
    service = VarietyService(db_session)
    assert service.calculate_variety_bonus_pct(0.0) == 0.0
    assert service.calculate_variety_bonus_pct(1.0) == pytest.approx(0.30)


def test_diminishing_returns_matches_pipeline_formula(db_session: Session) -> None:
    user = _create_user(db_session)
    tracking = StrategyTracking(
        user_id=user.id,
        strategy_streaks_json=json.dumps(
            {"study": {"count": 4, "last_day": "2026-03-10"}}
        ),
    )
    db_session.add(tracking)
    db_session.commit()

    service = DiminishingReturnsService(db_session)
    assert service.get_strategy_penalty("study", tracking) == pytest.approx(0.90)
    assert service.apply_diminishing_returns_to_xp(100, "study", user.id) == 90


def test_refresh_window_zeroes_variety_bonus_when_structured_row_missing(
    db_session: Session,
) -> None:
    user = _create_user(db_session)
    entry = JournalEntry(
        user_id=user.id,
        content="I studied and shipped code.",
        entry_type="text",
        status="completed",
        created_at=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(entry)
    db_session.commit()

    tracking = BalanceWindowService(db_session).refresh_window(
        user.id,
        datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc),
    )

    assert tracking.variety_score == 0.0
    assert tracking.variety_bonus_pct == 0.0
    assert tracking.strategy_streaks_json == "{}"


def test_harmony_balance_requires_entry_to_address_lowest_dimension(
    db_session: Session,
) -> None:
    user = _create_user(db_session)
    db_session.add(
        HarmonyDimension(
            user_id=user.id,
            physical=1.0,
            mental=1.0,
            social=1.0,
            productivity=1.0,
            rest=0.20,
            growth=1.0,
            creative=1.0,
            overall_balance=0.885714,
        )
    )
    entry = JournalEntry(
        user_id=user.id,
        content="I slept, rested, and relaxed today.",
        entry_type="text",
        status="completed",
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(entry)
    db_session.commit()

    detector = StrategyDetector(db_session)
    rest_structured = type(
        "_Structured",
        (),
        {
            "canonical_text": entry.content,
            "task_type": "rest",
            "energy_level": 4,
            "goal_relation": None,
            "skills_themes_involved": None,
        },
    )()
    productive_structured = type(
        "_Structured",
        (),
        {
            "canonical_text": "I wrote a lot of code for work.",
            "task_type": "analytical",
            "energy_level": 4,
            "goal_relation": None,
            "skills_themes_involved": None,
        },
    )()

    assert "harmony" in detector.detect_strategies(
        user_id=user.id,
        entry_id=entry.id,
        entry=entry,
        structured=rest_structured,
    )
    assert "harmony" not in detector.detect_strategies(
        user_id=user.id,
        entry_id=entry.id,
        entry=entry,
        structured=productive_structured,
    )


def test_harmony_balance_supports_theme_based_structured_entries(
    db_session: Session,
) -> None:
    user = _create_user(db_session, user_id="u-balance-theme")
    themes = ensure_user_themes(db_session, user.id)
    db_session.add(
        HarmonyDimension(
            user_id=user.id,
            physical=1.0,
            mental=1.0,
            social=1.0,
            productivity=1.0,
            rest=0.20,
            growth=1.0,
            creative=1.0,
            overall_balance=0.885714,
        )
    )
    entry = JournalEntry(
        user_id=user.id,
        content="I finally slowed down and protected my evening.",
        entry_type="text",
        status="completed",
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(entry)
    db_session.commit()

    detector = StrategyDetector(db_session)
    rest_theme_structured = type(
        "_Structured",
        (),
        {
            "canonical_text": entry.content,
            "task_type": None,
            "energy_level": 5,
            "goal_relation": None,
            "skills_themes_involved": json.dumps(
                [{"kind": "theme", "id": themes["Rest"].id}]
            ),
        },
    )()

    assert "harmony" in detector.detect_strategies(
        user_id=user.id,
        entry_id=entry.id,
        entry=entry,
        structured=rest_theme_structured,
    )
