"""Integration checks for canonical anomaly and personality APIs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.anomaly import AnomalyScore
from src.db.models.journal_entry import JournalEntry
from src.db.models.personality import PersonalityMessage, PersonalityState
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
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        username="week6_api",
        email="week6-api@example.com",
        password_hash="hash",
        timezone="UTC",
        home_country="US",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def completed_entry(db_session: Session, seeded_user: User) -> JournalEntry:
    entry = JournalEntry(
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        user_id=seeded_user.id,
        content="I shipped the anomaly and personality integration tests.",
        entry_type="text",
        status="completed",
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(entry)
    db_session.commit()
    return entry


@pytest.fixture
def processing_entry(db_session: Session, seeded_user: User) -> JournalEntry:
    entry = JournalEntry(
        id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        user_id=seeded_user.id,
        content="Still processing this entry.",
        entry_type="text",
        status="processing",
    )
    db_session.add(entry)
    db_session.commit()
    return entry


def test_recent_anomalies_and_entry_lookup_return_canonical_payloads(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
    completed_entry: JournalEntry,
) -> None:
    older_entry = JournalEntry(
        id="dddddddd-dddd-dddd-dddd-dddddddddddd",
        user_id=seeded_user.id,
        content="A second completed entry.",
        entry_type="text",
        status="completed",
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(older_entry)
    db_session.flush()
    db_session.add_all(
        [
            AnomalyScore(
                user_id=seeded_user.id,
                entry_id=completed_entry.id,
                score=8.7,
                troll_multiplier=2.125,
                detection_factors=json.dumps(
                    {"components": ["novelty_spike", "rare_pattern"]}
                ),
                calculated_at=datetime(2026, 3, 13, 11, 30, tzinfo=timezone.utc),
            ),
            AnomalyScore(
                user_id=seeded_user.id,
                entry_id=older_entry.id,
                score=6.8,
                troll_multiplier=1.400001,
                detection_factors=json.dumps({"components": ["high_entropy"]}),
                calculated_at=datetime(2026, 3, 12, 11, 30, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    recent = client.get(
        "/api/v1/anomaly/recent",
        params={"user_id": seeded_user.id, "min_score": 6.0, "limit": 5},
    )
    assert recent.status_code == 200
    recent_payload = recent.json()
    assert recent_payload["total"] == 2
    assert [row["entry_id"] for row in recent_payload["anomalies"]] == [
        completed_entry.id,
        older_entry.id,
    ]
    assert recent_payload["anomalies"][0]["detection_factors"] == {
        "components": ["novelty_spike", "rare_pattern"]
    }
    assert recent_payload["anomalies"][0]["calculated_at"].endswith("Z")

    lookup = client.get(
        f"/api/v1/anomaly/{completed_entry.id}",
        params={"user_id": seeded_user.id},
    )
    assert lookup.status_code == 200
    lookup_payload = lookup.json()
    assert lookup_payload["missing"] is False
    assert lookup_payload["score"] == pytest.approx(8.7)
    assert lookup_payload["troll_multiplier"] == pytest.approx(2.125)


def test_anomaly_lookup_reports_missing_for_completed_entry_without_score(
    client: TestClient,
    seeded_user: User,
    completed_entry: JournalEntry,
) -> None:
    response = client.get(
        f"/api/v1/anomaly/{completed_entry.id}",
        params={"user_id": seeded_user.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "entry_id": completed_entry.id,
        "score": 0.0,
        "troll_multiplier": 1.0,
        "calculated_at": None,
        "missing": True,
        "detection_factors": None,
    }


def test_anomaly_lookup_rejects_unknown_or_incomplete_entries(
    client: TestClient,
    seeded_user: User,
    processing_entry: JournalEntry,
) -> None:
    missing = client.get(
        "/api/v1/anomaly/ffffffff-ffff-ffff-ffff-ffffffffffff",
        params={"user_id": seeded_user.id},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Entry not found"

    incomplete = client.get(
        f"/api/v1/anomaly/{processing_entry.id}",
        params={"user_id": seeded_user.id},
    )
    assert incomplete.status_code == 409
    assert incomplete.json()["detail"] == "Entry not completed"


def test_compute_anomaly_returns_existing_or_persists_new_score(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
    completed_entry: JournalEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = AnomalyScore(
        user_id=seeded_user.id,
        entry_id=completed_entry.id,
        score=7.2,
        troll_multiplier=1.8,
        detection_factors=json.dumps({"components": ["existing_score"]}),
        calculated_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(existing)
    db_session.commit()

    cached = client.post(
        f"/api/v1/anomaly/{completed_entry.id}/compute",
        params={"user_id": seeded_user.id},
    )
    assert cached.status_code == 200
    assert cached.json()["detection_factors"] == {"components": ["existing_score"]}

    db_session.delete(existing)
    db_session.commit()

    def _fake_compute(self, user_id: str, entry_id: str) -> dict[str, object]:
        assert user_id == seeded_user.id
        assert entry_id == completed_entry.id
        row = AnomalyScore(
            user_id=user_id,
            entry_id=entry_id,
            score=9.1,
            troll_multiplier=2.333333,
            detection_factors=json.dumps(
                {"components": ["surprise_cluster", "rare_combo"]}
            ),
            calculated_at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
        )
        db_session.add(row)
        return {
            "score": row.score,
            "troll_multiplier": row.troll_multiplier,
            "detection_factors": {"components": ["surprise_cluster", "rare_combo"]},
            "calculated_at": row.calculated_at,
        }

    monkeypatch.setattr(
        "src.api.routes.anomaly.AnomalyOrchestrator.compute_anomaly_score",
        _fake_compute,
    )

    computed = client.post(
        f"/api/v1/anomaly/{completed_entry.id}/compute",
        params={"user_id": seeded_user.id},
    )
    assert computed.status_code == 200
    payload = computed.json()
    assert payload["score"] == pytest.approx(9.1)
    assert payload["troll_multiplier"] == pytest.approx(2.333333)
    assert payload["missing"] is False
    assert payload["detection_factors"] == {
        "components": ["surprise_cluster", "rare_combo"]
    }


def test_compute_anomaly_returns_conflict_or_server_error(
    client: TestClient,
    seeded_user: User,
    completed_entry: JournalEntry,
    processing_entry: JournalEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conflict = client.post(
        f"/api/v1/anomaly/{processing_entry.id}/compute",
        params={"user_id": seeded_user.id},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "ENTRY_NOT_COMPLETED"

    def _boom(self, user_id: str, entry_id: str) -> dict[str, object]:
        raise RuntimeError(f"boom:{user_id}:{entry_id}")

    monkeypatch.setattr(
        "src.api.routes.anomaly.AnomalyOrchestrator.compute_anomaly_score",
        _boom,
    )
    failed = client.post(
        f"/api/v1/anomaly/{completed_entry.id}/compute",
        params={"user_id": seeded_user.id},
    )
    assert failed.status_code == 500
    assert "ANOMALY_COMPUTE_FAILED" in failed.json()["detail"]


def test_personality_state_endpoint_bootstraps_and_reuses_state(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
) -> None:
    first = client.get("/api/v1/personality/state", params={"user_id": seeded_user.id})
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["active_personality"] == "observer"
    assert first_payload["likability_scores"]["observer"] == 80

    state = db_session.query(PersonalityState).filter_by(user_id=seeded_user.id).one()
    state.active_personality = "coach"
    db_session.commit()

    second = client.get("/api/v1/personality/state", params={"user_id": seeded_user.id})
    assert second.status_code == 200
    assert second.json()["active_personality"] == "coach"


def test_personality_feedback_applies_multiplier_and_validates_input(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
    completed_entry: JournalEntry,
) -> None:
    state = PersonalityState(user_id=seeded_user.id, likability_coach=60)
    message = PersonalityMessage(
        id="eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        user_id=seeded_user.id,
        entry_id=completed_entry.id,
        personality="coach",
        message_type="entry_feedback",
        message_text="Keep going.",
        logical_slot_key="primary",
        context_data=json.dumps(
            {
                "multi_personality": {"impact_multiplier": 1.5},
                "selection_reason": "confidence_boost",
            }
        ),
    )
    db_session.add_all([state, message])
    db_session.commit()

    invalid = client.post(
        "/api/v1/personality/feedback",
        params={"user_id": seeded_user.id},
        json={"message_id": message.id, "feedback_type": "not_valid"},
    )
    assert invalid.status_code == 422
    assert "feedback_type must be one of" in invalid.json()["detail"]

    ok = client.post(
        "/api/v1/personality/feedback",
        params={"user_id": seeded_user.id},
        json={"message_id": message.id, "feedback_type": "thumbs_up"},
    )
    assert ok.status_code == 200
    payload = ok.json()
    assert payload == {
        "personality": "coach",
        "old_likability": 60,
        "new_likability": 67,
        "delta": 7,
        "impact_multiplier": 1.5,
    }

    db_session.refresh(state)
    assert state.likability_coach == 67


def test_personality_feedback_returns_404_for_missing_rows(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
    completed_entry: JournalEntry,
) -> None:
    db_session.add(PersonalityState(user_id=seeded_user.id))
    db_session.commit()

    response = client.post(
        "/api/v1/personality/feedback",
        params={"user_id": seeded_user.id},
        json={
            "message_id": "99999999-9999-9999-9999-999999999999",
            "feedback_type": "thumbs_down",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Message not found"

    state_only_message = PersonalityMessage(
        id="abababab-abab-abab-abab-abababababab",
        user_id=seeded_user.id,
        entry_id=completed_entry.id,
        personality="observer",
        message_type="entry_feedback",
        message_text="Noted.",
        logical_slot_key="secondary",
        context_data="{}",
    )
    db_session.delete(db_session.query(PersonalityState).filter_by(user_id=seeded_user.id).one())
    db_session.add(state_only_message)
    db_session.commit()

    missing_state = client.post(
        "/api/v1/personality/feedback",
        params={"user_id": seeded_user.id},
        json={
            "message_id": state_only_message.id,
            "feedback_type": "thumbs_down",
        },
    )
    assert missing_state.status_code == 404
    assert missing_state.json()["detail"] == "Personality state not found"


def test_personality_messages_endpoint_filters_and_parses_context(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
    completed_entry: JournalEntry,
) -> None:
    other_entry = JournalEntry(
        id="f1f1f1f1-f1f1-f1f1-f1f1-f1f1f1f1f1f1",
        user_id=seeded_user.id,
        content="A second completed personality entry.",
        entry_type="text",
        status="completed",
    )
    db_session.add(other_entry)
    db_session.flush()
    db_session.add_all(
        [
            PersonalityMessage(
                id="12121212-1212-1212-1212-121212121212",
                user_id=seeded_user.id,
                entry_id=completed_entry.id,
                personality="observer",
                message_type="entry_feedback",
                message_text="Structured and steady.",
                logical_slot_key="primary",
                context_data=json.dumps({"selection_reason": "baseline"}),
                created_at=datetime(2026, 3, 13, 9, 0, tzinfo=timezone.utc),
            ),
            PersonalityMessage(
                id="34343434-3434-3434-3434-343434343434",
                user_id=seeded_user.id,
                entry_id=other_entry.id,
                personality="therapist",
                message_type="safety_intervention",
                message_text="Pause and breathe.",
                logical_slot_key="safety",
                context_data=json.dumps({"severity": "medium"}),
                created_at=datetime(2026, 3, 13, 10, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    all_messages = client.get(
        "/api/v1/personality/messages",
        params={"user_id": seeded_user.id, "limit": 5},
    )
    assert all_messages.status_code == 200
    payload = all_messages.json()
    assert [row["id"] for row in payload] == [
        "34343434-3434-3434-3434-343434343434",
        "12121212-1212-1212-1212-121212121212",
    ]
    assert payload[0]["context_data"] == {"severity": "medium"}
    assert payload[0]["created_at"].endswith("Z")

    filtered = client.get(
        "/api/v1/personality/messages",
        params={"user_id": seeded_user.id, "entry_id": completed_entry.id, "limit": 5},
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert len(filtered_payload) == 1
    assert filtered_payload[0]["entry_id"] == completed_entry.id
