"""Integration checks for journal thread browsing APIs."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.journal_entry import JournalEntry
from src.db.models.user import User
from src.db.session import get_db


def _make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = session_local()
    session._test_engine = engine  # type: ignore[attr-defined]
    return session


def _dispose_session(session: Session) -> None:
    engine = session._test_engine  # type: ignore[attr-defined]
    session.close()
    engine.dispose()


def _client_with_db(db_session: Session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_journal_entries_list_returns_preview_and_question_state() -> None:
    db = _make_session()
    try:
        user = User(
            id="10101010-1010-1010-1010-101010101010",
            username="journal_threads",
            email="journal-threads@example.com",
            password_hash="hash",
            home_country="US",
        )
        db.add(user)
        db.add_all(
            [
                JournalEntry(
                    id="20202020-2020-2020-2020-202020202020",
                    user_id=user.id,
                    content="I drafted the thread UI and verified the recent entry navigator.",
                    entry_type="text",
                    status="completed",
                    question_state="answered",
                    created_at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
                ),
                JournalEntry(
                    id="30303030-3030-3030-3030-303030303030",
                    user_id=user.id,
                    content="A newer processing entry for the journal thread view.",
                    entry_type="text",
                    status="processing",
                    question_state="pending",
                    created_at=datetime(2026, 3, 13, 13, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        db.commit()

        with _client_with_db(db) as client:
            response = client.get(
                "/api/v1/journal/entries",
                params={"user_id": user.id, "limit": 10},
            )

        assert response.status_code == 200
        payload = response.json()
        assert [row["entry_id"] for row in payload] == [
            "30303030-3030-3030-3030-303030303030",
            "20202020-2020-2020-2020-202020202020",
        ]
        assert payload[0]["question_state"] == "pending"
        assert payload[0]["preview_text"] == "A newer processing entry for the journal thread view."
        assert payload[1]["question_state"] == "answered"
        assert payload[1]["word_count"] == 11
    finally:
        _dispose_session(db)
        app.dependency_overrides.clear()


def test_journal_entry_detail_requires_owning_user() -> None:
    db = _make_session()
    try:
        owner = User(
            id="40404040-4040-4040-4040-404040404040",
            username="entry_owner",
            email="entry-owner@example.com",
            password_hash="hash",
            home_country="US",
        )
        stranger = User(
            id="50505050-5050-5050-5050-505050505050",
            username="entry_stranger",
            email="entry-stranger@example.com",
            password_hash="hash",
            home_country="US",
        )
        entry = JournalEntry(
            id="60606060-6060-6060-6060-606060606060",
            user_id=owner.id,
            content="Full transcript content for the selected entry.",
            entry_type="text",
            status="completed",
            question_state="none",
            processing_duration_ms=3210,
            error_message=None,
            created_at=datetime(2026, 3, 13, 8, 15, tzinfo=timezone.utc),
        )
        db.add_all([owner, stranger, entry])
        db.commit()

        with _client_with_db(db) as client:
            ok = client.get(
                f"/api/v1/journal/entries/{entry.id}/detail",
                params={"user_id": owner.id},
            )
            forbidden = client.get(
                f"/api/v1/journal/entries/{entry.id}/detail",
                params={"user_id": stranger.id},
            )

        assert ok.status_code == 200
        ok_payload = ok.json()
        assert ok_payload["entry_id"] == entry.id
        assert ok_payload["content"] == entry.content
        assert ok_payload["question_state"] == "none"
        assert ok_payload["processing_duration_ms"] == 3210

        assert forbidden.status_code == 404
        assert forbidden.json()["detail"] == f"Entry '{entry.id}' not found."
    finally:
        _dispose_session(db)
        app.dependency_overrides.clear()
