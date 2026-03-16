"""Canonical Section 13 API contract tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.db.base import Base
import src.db.models  # noqa: F401
from src.db.models.journal_entry import JournalEntry
from src.db.models.processing import EntryIdempotencyClaim, ProcessingJob
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
        id="11111111-1111-1111-1111-111111111111",
        username="entry_contract",
        email="entry-contract@example.com",
        password_hash="hash",
        home_country="US",
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_async_ack_and_poll_replay_contract(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_background(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "src.api.routes.entries._process_reserved_entry_background",
        _noop_background,
    )

    payload = {
        "user_id": seeded_user.id,
        "content": "I drafted the canonical route tests and reviewed the payload contract.",
        "idempotency_key": "contract-async-1",
        "processing_mode": "async",
    }
    response = client.post("/api/v1/entries", json=payload)

    assert response.status_code == 202
    ack = response.json()
    assert ack["result_type"] == "ack"
    assert ack["status"] == "pending"
    assert ack["entry_id"]
    assert ack["job_id"]
    assert ack["created_at_utc"]
    assert ack["updated_at_utc"]
    assert ack["attempt_count"] == 0
    assert ack["poll_path"].endswith(ack["job_id"])

    poll = client.get(
        f"/api/v1/entry-jobs/{ack['job_id']}",
        params={"user_id": seeded_user.id},
    )
    assert poll.status_code == 200
    poll_payload = poll.json()
    assert poll_payload["status"] == "in_progress"
    assert poll_payload["created_at_utc"]
    assert poll_payload["updated_at_utc"]

    replay = client.post("/api/v1/entries", json=payload)
    assert replay.status_code == 202
    replay_payload = replay.json()
    assert replay_payload["replayed"] is True
    assert replay_payload["job_id"] == ack["job_id"]

    claim = db_session.query(EntryIdempotencyClaim).one()
    job = db_session.query(ProcessingJob).one()
    assert claim.processing_job_id == job.id
    assert claim.entry_id == ack["entry_id"]


def test_sync_mode_returns_terminal_success_and_replays(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_process_entry(
        self,
        entry_id: str,
        user_id: str,
        *,
        idempotency_key: str | None = None,
        job_id: str | None = None,
        **_kwargs,
    ) -> dict[str, object]:
        entry = db_session.query(JournalEntry).filter(JournalEntry.id == entry_id).one()
        job = db_session.query(ProcessingJob).filter(ProcessingJob.id == job_id).one()
        claim = (
            db_session.query(EntryIdempotencyClaim)
            .filter(EntryIdempotencyClaim.idempotency_key == idempotency_key)
            .one()
        )
        result = {
            "result_type": "success",
            "status": "completed",
            "entry_id": entry_id,
            "user_id": user_id,
            "job_id": job.id,
            "processing_run_id": job.processing_run_id,
            "poll_path": f"/api/v1/entry-jobs/{job.id}",
            "message": "Primary reply",
            "message_id": "msg-primary",
            "personality": "coach",
            "report_result": {
                "personality": "system",
                "message_type": "report_summary",
                "logical_slot_key": "system_report",
                "message_id": "msg-system",
                "inserted": True,
                "context_data": {
                    "report_kind": "daily",
                    "completion_status": "partial",
                    "missing_sections": ["insight"],
                    "section_statuses": {
                        "signals": {"status": "present", "details": ["skills: Python"]},
                        "insight": {"status": "missing", "details": ["no insight generated"]},
                        "personality_reply": {"status": "present", "details": ["personality: coach"]},
                    },
                    "approx_processing_ms": 1234,
                },
            },
            "step_trace": [
                {
                    "step_name": "step_01_validate_input",
                    "status": "succeeded",
                    "duration_ms": 0,
                    "critical": True,
                    "fallback_used": False,
                    "error_code": None,
                    "error_message": None,
                    "output": {"entry_id": entry_id},
                    "not_persisted_reason": None,
                }
            ],
            "quality": {
                "degraded": False,
                "degraded_codes": [],
                "dependency_states": {"ollama": "ok", "qdrant": "ok", "rag": "ok"},
            },
            "meta": {
                "degraded": False,
                "degraded_codes": [],
                "dependency_states": {"ollama": "ok", "qdrant": "ok", "rag": "ok"},
            },
            "provenance": {
                "processing_run_id": job.processing_run_id,
                "pipeline_version": "test-v1",
                "ruleset_version": "test-rules",
            },
            "personality_messages": [
                {
                    "id": "msg-primary",
                    "entry_id": entry_id,
                    "personality": "coach",
                    "message_type": "entry_feedback",
                    "message_text": "Primary reply",
                    "logical_slot_key": "primary",
                    "context_data": {},
                    "multi_personality": {
                        "is_primary": True,
                        "primary_personality": "coach",
                        "impact_multiplier": 1.0,
                    },
                    "created_at": "2026-03-13T12:00:00.000Z",
                },
                {
                    "id": "msg-secondary",
                    "entry_id": entry_id,
                    "personality": "observer",
                    "message_type": "entry_feedback",
                    "message_text": "Secondary reply",
                    "logical_slot_key": "secondary",
                    "context_data": {},
                    "multi_personality": {
                        "is_primary": False,
                        "primary_personality": "coach",
                        "impact_multiplier": 0.5,
                    },
                    "created_at": "2026-03-13T12:00:01.000Z",
                },
                {
                    "id": "msg-system",
                    "entry_id": entry_id,
                    "personality": "system",
                    "message_type": "report_summary",
                    "message_text": "SYSTEM REPORT CHECKLIST\n\n[Signals] present\n- skills: Python\n\n[Insight] missing",
                    "logical_slot_key": "system_report",
                    "context_data": {
                        "report_kind": "daily",
                        "completion_status": "partial",
                        "missing_sections": ["insight"],
                    },
                    "multi_personality": {
                        "is_primary": False,
                        "primary_personality": "system",
                        "impact_multiplier": 0.5,
                    },
                    "created_at": "2026-03-13T12:00:02.000Z",
                },
            ],
        }
        entry.status = "completed"
        job.status = "succeeded"
        job.attempt_count = 1
        job.result_json = json.dumps(result, sort_keys=True)
        job.final_payload_hash = "hash"
        claim.status = "completed"
        claim.processing_job_id = job.id
        claim.processing_run_id = job.processing_run_id
        claim.result_pointer_json = json.dumps(
            {
                "schema_version": 1,
                "job_id": job.id,
                "entry_id": entry_id,
                "status": "completed",
                "poll_path": f"/api/v1/entry-jobs/{job.id}",
                "terminal_result_hash": "hash",
            },
            sort_keys=True,
        )
        db_session.commit()
        return result

    monkeypatch.setattr(
        "src.api.routes.entries.JournalEntryPipeline.process_entry",
        _fake_process_entry,
    )

    payload = {
        "user_id": seeded_user.id,
        "content": "I completed the sync execution path and persisted the canonical replay data.",
        "idempotency_key": "contract-sync-1",
        "processing_mode": "sync",
    }
    response = client.post("/api/v1/entries", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert [row["id"] for row in result["personality_messages"]] == [
        "msg-primary",
        "msg-secondary",
        "msg-system",
    ]
    assert result["message"] == "Primary reply"
    assert result["message_id"] == "msg-primary"
    assert result["personality"] == "coach"
    assert result["report_result"]["message_id"] == "msg-system"
    assert result["report_result"]["context_data"]["report_kind"] == "daily"

    poll = client.get(
        f"/api/v1/entry-jobs/{result['job_id']}",
        params={"user_id": seeded_user.id},
    )
    assert poll.status_code == 200
    poll_payload = poll.json()
    assert poll_payload["status"] == "completed"
    assert poll_payload["terminal_result"] == result
    assert [row["id"] for row in poll_payload["terminal_result"]["personality_messages"]] == [
        "msg-primary",
        "msg-secondary",
        "msg-system",
    ]
    assert poll_payload["terminal_result"]["message"] == "Primary reply"
    assert poll_payload["terminal_result"]["message_id"] == "msg-primary"
    assert poll_payload["terminal_result"]["personality"] == "coach"
    assert poll_payload["terminal_result"]["report_result"]["message_id"] == "msg-system"

    replay = client.post("/api/v1/entries", json=payload)
    assert replay.status_code == 200
    replay_payload = replay.json()
    assert replay_payload["status"] == "completed"
    assert replay_payload["replayed"] is True


def test_failed_replay_and_poll_terminal_failure_contract(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
) -> None:
    entry = JournalEntry(
        id="22222222-2222-2222-2222-222222222222",
        user_id=seeded_user.id,
        content="This entry already failed in a prior attempt.",
        entry_type="text",
        status="failed",
    )
    job = ProcessingJob(
        id="33333333-3333-3333-3333-333333333333",
        user_id=seeded_user.id,
        entry_id=entry.id,
        step_name="entry_pipeline",
        processing_run_id="44444444-4444-4444-4444-444444444444",
        status="failed",
        attempt_count=2,
        final_error_code="ENTRY_PIPELINE_FAILED",
        result_json=json.dumps(
            {
                "result_type": "failure",
                "status": "failed",
                "entry_id": entry.id,
                "job_id": "33333333-3333-3333-3333-333333333333",
                "processing_run_id": "44444444-4444-4444-4444-444444444444",
                "retryable": False,
                "terminal_error": {
                    "code": "ENTRY_PIPELINE_FAILED",
                    "message": "processing failed",
                },
                "noncritical_errors": [],
            },
            sort_keys=True,
        ),
        final_payload_hash="terminal-hash",
    )
    claim = EntryIdempotencyClaim(
        user_id=seeded_user.id,
        idempotency_key="contract-failed-1",
        request_payload_hash="request-hash",
        entry_id=entry.id,
        processing_job_id=job.id,
        processing_run_id=job.processing_run_id,
        result_pointer_json=json.dumps(
            {
                "schema_version": 1,
                "job_id": job.id,
                "entry_id": entry.id,
                "status": "failed_terminal",
                "poll_path": f"/api/v1/entry-jobs/{job.id}",
                "terminal_result_hash": "terminal-hash",
            },
            sort_keys=True,
        ),
        status="failed_terminal",
    )
    db_session.add_all([entry, job])
    db_session.commit()
    db_session.add(claim)
    db_session.commit()

    replay = client.post(
        "/api/v1/entries",
        json={
            "user_id": seeded_user.id,
            "content": "This entry already failed in a prior attempt.",
            "idempotency_key": "contract-failed-1",
        },
    )
    assert replay.status_code == 200
    replay_payload = replay.json()
    assert replay_payload["result_type"] == "failure"
    assert replay_payload["status"] == "failed"
    assert replay_payload["replayed"] is True

    poll = client.get(f"/api/v1/entry-jobs/{job.id}", params={"user_id": seeded_user.id})
    assert poll.status_code == 200
    poll_payload = poll.json()
    assert poll_payload["status"] == "failed_terminal"
    assert poll_payload["last_error_code"] == "ENTRY_PIPELINE_FAILED"
    assert poll_payload["terminal_result_pointer"]["terminal_result_hash"] == "terminal-hash"


def test_auto_mode_and_sync_fallback_cover_canonical_branches(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _sync_then_raise(
        self,
        entry_id: str,
        user_id: str,
        *,
        job_id: str | None = None,
        **_kwargs,
    ) -> dict[str, object]:
        job = db_session.query(ProcessingJob).filter(ProcessingJob.id == job_id).one()
        job.status = "failed"
        job.result_json = json.dumps(
            {
                "result_type": "failure",
                "status": "failed",
                "entry_id": entry_id,
                "user_id": user_id,
                "job_id": job.id,
                "processing_run_id": job.processing_run_id,
                "retryable": False,
                "terminal_error": {
                    "code": "ENTRY_PIPELINE_FAILED",
                    "message": "sync fallback",
                },
                "noncritical_errors": [],
            },
            sort_keys=True,
        )
        db_session.commit()
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "src.api.routes.entries.JournalEntryPipeline.process_entry",
        _sync_then_raise,
    )

    sync_response = client.post(
        "/api/v1/entries",
        json={
            "user_id": seeded_user.id,
            "content": "short auto sync payload",
            "idempotency_key": "auto-sync-fallback-1",
            "processing_mode": "auto",
        },
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["terminal_error"]["message"] == "sync fallback"

    async def _noop_background(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "src.api.routes.entries._process_reserved_entry_background",
        _noop_background,
    )

    async_response = client.post(
        "/api/v1/entries",
        json={
            "user_id": seeded_user.id,
            "content": "audio transcript payload",
            "content_type": "audio_transcript",
            "idempotency_key": "auto-async-audio-1",
            "processing_mode": "auto",
        },
    )
    assert async_response.status_code == 202
    assert async_response.json()["result_type"] == "ack"

    long_response = client.post(
        "/api/v1/entries",
        json={
            "user_id": seeded_user.id,
            "content": "x" * 4501,
            "idempotency_key": "auto-async-long-1",
            "processing_mode": "auto",
        },
    )
    assert long_response.status_code == 202
    assert long_response.json()["result_type"] == "ack"


def test_entry_processing_validation_and_missing_resource_edges(
    client: TestClient,
    db_session: Session,
    seeded_user: User,
) -> None:
    missing_user = client.post(
        "/api/v1/entries",
        json={
            "user_id": "99999999-9999-9999-9999-999999999999",
            "content": "unknown user",
            "idempotency_key": "missing-user-1",
        },
    )
    assert missing_user.status_code == 404
    assert "not found" in missing_user.json()["detail"]

    invalid = client.post(
        "/api/v1/entries",
        json={
            "user_id": seeded_user.id,
            "content": "   ",
            "idempotency_key": "   ",
        },
    )
    assert invalid.status_code == 422

    orphan_claim = EntryIdempotencyClaim(
        user_id=seeded_user.id,
        idempotency_key="orphan-claim-1",
        request_payload_hash="hash",
        processing_job_id="55555555-5555-5555-5555-555555555555",
        processing_run_id="66666666-6666-6666-6666-666666666666",
        status="in_progress",
    )
    orphan_entry = JournalEntry(
        id="88888888-8888-8888-8888-888888888888",
        user_id=seeded_user.id,
        content="stale orphan entry",
        entry_type="text",
        status="processing",
    )
    orphan_job = ProcessingJob(
        id="55555555-5555-5555-5555-555555555555",
        user_id=seeded_user.id,
        entry_id=orphan_entry.id,
        step_name="entry_pipeline",
        processing_run_id="66666666-6666-6666-6666-666666666666",
        status="in_progress",
        request_payload_hash="hash",
    )
    db_session.add_all([orphan_entry, orphan_job])
    db_session.commit()
    db_session.add(orphan_claim)
    db_session.commit()
    db_session.delete(orphan_job)
    db_session.commit()

    conflict = client.post(
        "/api/v1/entries",
        json={
            "user_id": seeded_user.id,
            "content": "orphan claim replay",
            "idempotency_key": "orphan-claim-1",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "Idempotency claim has no job"

    missing_job = client.get(
        "/api/v1/entry-jobs/77777777-7777-7777-7777-777777777777",
        params={"user_id": seeded_user.id},
    )
    assert missing_job.status_code == 404
    assert missing_job.json()["detail"] == "Job not found"
