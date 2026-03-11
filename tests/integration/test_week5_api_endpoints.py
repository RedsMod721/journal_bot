from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.forgiveness import ForgivenessConfig
from src.db.models.harmony import HarmonyDimension, HarmonySnapshot
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.user import User
from src.db.session import get_db


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


@pytest.fixture
def client(db_session: Session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_user(db_session: Session) -> User:
    user = User(
        id="week5-user",
        username="week5",
        email="week5@example.com",
        password_hash="hash",
        timezone="Europe/Paris",
        home_country="US",
    )
    db_session.add(user)
    db_session.flush()
    config = ForgivenessConfig(
        user_id=user.id,
        preset="balanced",
        skill_decay_rate=0.05,
        insight_decay_rate=0.10,
        skill_grace_period_days=7,
        insight_grace_period_days=3,
        critical_staleness_threshold=0.80,
    )
    db_session.add(config)
    db_session.flush()
    user.forgiveness_config_id = config.id
    db_session.commit()
    return user


@pytest.fixture
def demo_user(db_session: Session) -> User:
    user = User(
        id="3f0f158d-d814-43f9-b035-5f6b43edeb41",
        username="maya_motion",
        email="maya_motion@placeholder.local",
        password_hash="hash",
        timezone="UTC",
        home_country="FR",
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_harmony_dimensions_endpoint_refreshes_stale_rows(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
) -> None:
    db_session.add(
        HarmonyDimension(
            user_id=seeded_user.id,
            physical=0.0,
            mental=0.0,
            social=0.0,
            productivity=0.0,
            rest=0.0,
            growth=0.0,
            creative=0.0,
            overall_balance=0.0,
        )
    )
    db_session.commit()

    response = client.get("/api/harmony/dimensions", params={"user_id": seeded_user.id})
    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_balance"] == pytest.approx(0.5)
    assert payload["dimensions"]["rest"] == pytest.approx(0.5)


def test_harmony_overwork_status_returns_effective_read_stage(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
) -> None:
    now = datetime.now(timezone.utc)
    for offset in range(4):
        entry = JournalEntry(
            user_id=seeded_user.id,
            content="Work sprint",
            entry_type="text",
            status="completed",
            created_at=now - timedelta(days=offset + 1),
        )
        db_session.add(entry)
        db_session.flush()
        db_session.add(
            JournalEntryStructured(
                user_id=seeded_user.id,
                entry_id=entry.id,
                canonical_text="Work sprint",
                task_type="administrative",
                energy_level=3,
            )
        )
    db_session.add(
        HarmonyDimension(
            user_id=seeded_user.id,
            overwork_stage=0,
            overwork_consecutive_days=4,
        )
    )
    db_session.commit()

    response = client.get("/api/harmony/overwork-status", params={"user_id": seeded_user.id})
    assert response.status_code == 200
    payload = response.json()
    assert payload["stage"] == 2
    assert payload["stage_name"] == "Warning"


def test_harmony_snapshots_use_user_local_day_for_filtering(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
) -> None:
    snapshot_date = datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=1))
    ).date()
    db_session.add(
        HarmonySnapshot(
            user_id=seeded_user.id,
            snapshot_date=snapshot_date,
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
    db_session.commit()

    response = client.get(
        "/api/harmony/snapshots",
        params={"user_id": seeded_user.id, "days": 2},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload


def test_harmony_dimensions_read_path_does_not_advance_overwork_persistence(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
) -> None:
    now = datetime.now(timezone.utc)
    for offset in range(3):
        entry = JournalEntry(
            user_id=seeded_user.id,
            content="Work sprint",
            entry_type="text",
            status="completed",
            created_at=now - timedelta(days=offset + 1),
        )
        db_session.add(entry)
        db_session.flush()
        db_session.add(
            JournalEntryStructured(
                user_id=seeded_user.id,
                entry_id=entry.id,
                canonical_text="Work sprint",
                task_type="administrative",
                energy_level=3,
            )
        )
    db_session.commit()

    response = client.get("/api/harmony/dimensions", params={"user_id": seeded_user.id})
    assert response.status_code == 200
    row = db_session.query(HarmonyDimension).filter(HarmonyDimension.user_id == seeded_user.id).one()
    assert row.overwork_last_evaluated_local_date is None


def test_harmony_dimensions_demo_profile_falls_back_to_seed_payload(
    client: TestClient,
    demo_user: User,
) -> None:
    response = client.get("/api/harmony/dimensions", params={"user_id": demo_user.id})
    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == demo_user.id
    assert payload["overall_balance"] == pytest.approx(0.88445)
    assert payload["dimensions"]["physical"] == pytest.approx(1.0)
    assert payload["overwork_stage"] == 0


def test_balance_variety_demo_profile_falls_back_to_seed_payload(
    client: TestClient,
    demo_user: User,
) -> None:
    response = client.get("/api/balance/variety", params={"user_id": demo_user.id})
    assert response.status_code == 200
    payload = response.json()
    assert payload["variety_score"] == pytest.approx(0.355245)
    assert payload["variety_bonus_pct"] == pytest.approx(0.03786)
    assert payload["strategy_counts"]["study"] == 2
    assert payload["strategy_counts"]["grind"] == 4
