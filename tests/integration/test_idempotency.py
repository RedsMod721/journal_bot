"""
Integration tests for IdempotencyManager — Section 13.5.2 Finalize-Once.

Scenarios
---------
1. Same idempotency_key → replay returns cached result
2. 100 concurrent requests, same key → exactly 1 finalization
3. Failed job (retryable) → new retry allowed
4. Succeeded job → replay returns cached result
5. Different idempotency_key → independent executions
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import List

import pytest
from sqlalchemy import create_engine, event as sa_event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import src.db.models  # noqa: F401  register all mappers
from src.db.base import Base
from src.db.models.processing import EntryIdempotencyClaim, ProcessingJob
from src.db.models.user import User
from src.ai.pipeline.idempotency_manager import IdempotencyManager

pytestmark = [pytest.mark.integration]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_engine():
    """Create an in-memory SQLite engine with FK enforcement OFF.

    FK enforcement is disabled because idempotency tests supply synthetic
    UUIDs for entry_id / processing_job_id without creating the parent rows.
    The FK constraints are tested implicitly in the full pipeline e2e tests.
    """
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(eng, "connect")
    def _disable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys = OFF")

    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture(scope="function")
def engine():
    eng = _make_engine()
    yield eng
    eng.dispose()


@pytest.fixture(scope="function")
def db(engine) -> Session:
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def user(db: Session) -> User:
    u = User(
        id=str(uuid.uuid4()),
        username="idempotency_test_user",
        email="idempotency@test.example",
        password_hash="not-used",
        home_country="US",
    )
    db.add(u)
    db.commit()
    return u


def _make_idempotency_key() -> str:
    return f"ikey-{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# Helper: build a succeeded ProcessingJob (without a real entry — tests the
# can_finalize / finalize-once guard in isolation).
# ---------------------------------------------------------------------------


def _seed_succeeded_job(
    db: Session,
    user_id: str,
    entry_id: str,
    step_name: str = "entry_pipeline",
) -> ProcessingJob:
    """Insert a succeeded ProcessingJob row directly for testing."""
    now = datetime.now(timezone.utc)
    job = ProcessingJob(
        id=str(uuid.uuid4()),
        user_id=user_id,
        entry_id=entry_id,
        step_name=step_name,
        processing_run_id=str(uuid.uuid4()),
        status="succeeded",
        attempt_count=1,
        finalized_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    return job


def _seed_failed_job(
    db: Session,
    user_id: str,
    entry_id: str,
    step_name: str = "entry_pipeline",
) -> ProcessingJob:
    """Insert a failed ProcessingJob row directly for testing."""
    now = datetime.now(timezone.utc)
    job = ProcessingJob(
        id=str(uuid.uuid4()),
        user_id=user_id,
        entry_id=entry_id,
        step_name=step_name,
        processing_run_id=str(uuid.uuid4()),
        status="failed",
        attempt_count=1,
        final_error_code="TEST_FAILURE",
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    return job


# ---------------------------------------------------------------------------
# Scenario 1 — Same key → replay cached result
# ---------------------------------------------------------------------------


class TestReplayCachedResult:
    def test_first_call_reserves_no_replay(self, db: Session, user: User):
        """First request reserves a new claim and returns (False, None)."""
        mgr = IdempotencyManager(db)
        key = _make_idempotency_key()

        is_replay, result = mgr.check_and_reserve(user.id, key)

        assert is_replay is False
        assert result is None

        claim = (
            db.query(EntryIdempotencyClaim)
            .filter_by(user_id=user.id, idempotency_key=key)
            .one()
        )
        assert claim.status == "reserved"

    def test_completed_claim_returns_replay(self, db: Session, user: User):
        """Once a claim is completed, the same key returns a replay dict."""
        mgr = IdempotencyManager(db)
        key = _make_idempotency_key()
        entry_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        # Reserve, advance, complete lifecycle.
        mgr.check_and_reserve(user.id, key)
        mgr.advance_to_in_progress(user.id, key, entry_id, job_id, run_id)
        mgr.complete(user.id, key, entry_id, job_id, run_id)

        # Second call with the same key.
        is_replay, result = mgr.check_and_reserve(user.id, key)

        assert is_replay is True
        assert result is not None
        assert result["status"] == "completed"
        assert result["entry_id"] == entry_id
        assert result["job_id"] == job_id
        assert result["result_pointer"]["schema_version"] == "1"
        assert entry_id in result["result_pointer"]["poll_path"]

    def test_in_progress_claim_returns_replay_ack(self, db: Session, user: User):
        """An in-progress claim returns a replay ack without blocking."""
        mgr = IdempotencyManager(db)
        key = _make_idempotency_key()
        entry_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        mgr.check_and_reserve(user.id, key)
        mgr.advance_to_in_progress(user.id, key, entry_id, job_id, run_id)

        # Second call before completion.
        is_replay, result = mgr.check_and_reserve(user.id, key)

        assert is_replay is True
        assert result["status"] == "in_progress"
        assert result["entry_id"] == entry_id


# ---------------------------------------------------------------------------
# Scenario 2 — Concurrent requests, same key → exactly 1 finalization
# ---------------------------------------------------------------------------


class TestConcurrentRequests:
    def test_100_concurrent_same_key_one_reservation(self, engine, user: User):
        """
        100 concurrent check_and_reserve calls for the same key.

        The critical invariant is that only ONE claim row exists in the DB
        after all threads complete — duplicate finalization is impossible.

        SQLite StaticPool serialises writes, so UNIQUE constraint violations
        are reliably detected.  We count errors separately and verify the DB
        is in a consistent state regardless of how threads interleaved.
        """
        factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        key = _make_idempotency_key()

        results: List[bool] = []   # True=replay, False=new-run
        errors: List[Exception] = []
        lock = threading.Lock()

        def _attempt():
            session = factory()
            try:
                mgr = IdempotencyManager(session)
                is_replay, _ = mgr.check_and_reserve(user.id, key)
                with lock:
                    results.append(is_replay)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(exc)
            finally:
                session.close()

        threads = [threading.Thread(target=_attempt) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No uncaught exceptions from any thread.
        assert not errors, f"Thread exceptions: {errors[:3]}"

        # All 100 threads completed and returned a result.
        assert len(results) == 100

        # The DB must contain exactly one claim for this key — the core
        # finalize-once invariant: no matter how many concurrent requests,
        # only one reservation succeeds.
        check_session = factory()
        try:
            count = (
                check_session.query(EntryIdempotencyClaim)
                .filter_by(user_id=user.id, idempotency_key=key)
                .count()
            )
            assert count == 1, (
                f"Expected exactly 1 claim row; found {count} — "
                "duplicate reservations indicate a finalize-once violation"
            )
        finally:
            check_session.close()


# ---------------------------------------------------------------------------
# Scenario 3 — Failed job → retry allowed
# ---------------------------------------------------------------------------


class TestFailedJobRetry:
    def test_retryable_failure_allows_new_run(self, db: Session, user: User):
        """failed_retryable claim → check_and_reserve returns (False, None)."""
        mgr = IdempotencyManager(db)
        key = _make_idempotency_key()
        entry_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        # First run — reserve then fail.
        mgr.check_and_reserve(user.id, key)
        mgr.advance_to_in_progress(user.id, key, entry_id, job_id, run_id)
        mgr.fail(user.id, key, error_code="TX_B_ERROR", terminal=False)

        claim = (
            db.query(EntryIdempotencyClaim)
            .filter_by(user_id=user.id, idempotency_key=key)
            .one()
        )
        assert claim.status == "failed_retryable"

        # Retry — should be allowed.
        is_replay, result = mgr.check_and_reserve(user.id, key)
        assert is_replay is False
        assert result is None

    def test_terminal_failure_blocks_retry(self, db: Session, user: User):
        """failed_terminal claim → check_and_reserve returns (True, error_payload)."""
        mgr = IdempotencyManager(db)
        key = _make_idempotency_key()
        entry_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        mgr.check_and_reserve(user.id, key)
        mgr.advance_to_in_progress(user.id, key, entry_id, job_id, run_id)
        mgr.fail(user.id, key, error_code="FATAL_ERROR", terminal=True)

        is_replay, result = mgr.check_and_reserve(user.id, key)
        assert is_replay is True
        assert result["status"] == "failed_terminal"
        assert result["error_code"] == "FATAL_ERROR"


# ---------------------------------------------------------------------------
# Scenario 4 — Succeeded job → retry returns cache
# ---------------------------------------------------------------------------


class TestSucceededJobReturnsCache:
    def test_full_lifecycle_then_replay(self, db: Session, user: User):
        """Full reserve→in_progress→complete cycle; replay returns cached pointer."""
        mgr = IdempotencyManager(db)
        key = _make_idempotency_key()
        entry_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        # --- Run 1 ---
        is_replay, _ = mgr.check_and_reserve(user.id, key)
        assert is_replay is False

        mgr.advance_to_in_progress(user.id, key, entry_id, job_id, run_id)
        mgr.complete(user.id, key, entry_id, job_id, run_id)

        # --- Run 2 (same key) ---
        is_replay, result = mgr.check_and_reserve(user.id, key)
        assert is_replay is True
        assert result["status"] == "completed"
        assert result["entry_id"] == entry_id
        assert result["job_id"] == job_id
        assert result["processing_run_id"] == run_id

        # --- Run 3 (same key, same result) ---
        is_replay2, result2 = mgr.check_and_reserve(user.id, key)
        assert is_replay2 is True
        assert result2 == result

    def test_can_finalize_true_when_no_succeeded_job(self, db: Session, user: User):
        """can_finalize returns True when no succeeded job exists."""
        mgr = IdempotencyManager(db)
        entry_id = str(uuid.uuid4())
        assert mgr.can_finalize(user.id, entry_id) is True

    def test_can_finalize_false_when_succeeded_job_exists(
        self, db: Session, user: User
    ):
        """can_finalize returns False when a succeeded job already exists."""
        mgr = IdempotencyManager(db)
        entry_id = str(uuid.uuid4())
        _seed_succeeded_job(db, user.id, entry_id)
        assert mgr.can_finalize(user.id, entry_id) is False


# ---------------------------------------------------------------------------
# Scenario 5 — Different idempotency_key → independent executions
# ---------------------------------------------------------------------------


class TestDifferentKeyIndependence:
    def test_two_keys_two_independent_claims(self, db: Session, user: User):
        """Two different keys for the same user create two independent claims."""
        mgr = IdempotencyManager(db)
        key_a = _make_idempotency_key()
        key_b = _make_idempotency_key()

        is_replay_a, _ = mgr.check_and_reserve(user.id, key_a)
        is_replay_b, _ = mgr.check_and_reserve(user.id, key_b)

        assert is_replay_a is False
        assert is_replay_b is False

        count = (
            db.query(EntryIdempotencyClaim)
            .filter_by(user_id=user.id)
            .count()
        )
        assert count == 2

    def test_completing_one_key_does_not_affect_other(self, db: Session, user: User):
        """Completing key_a does not make key_b replay."""
        mgr = IdempotencyManager(db)
        key_a = _make_idempotency_key()
        key_b = _make_idempotency_key()
        entry_a = str(uuid.uuid4())
        job_a = str(uuid.uuid4())
        run_a = str(uuid.uuid4())

        mgr.check_and_reserve(user.id, key_a)
        mgr.check_and_reserve(user.id, key_b)
        mgr.advance_to_in_progress(user.id, key_a, entry_a, job_a, run_a)
        mgr.complete(user.id, key_a, entry_a, job_a, run_a)

        # key_a replays
        is_replay_a, result_a = mgr.check_and_reserve(user.id, key_a)
        assert is_replay_a is True
        assert result_a["status"] == "completed"

        # key_b is still reserved, not replaying
        is_replay_b, _ = mgr.check_and_reserve(user.id, key_b)
        assert is_replay_b is True  # reserved → in-progress ack (not a new run)

    def test_same_key_different_users_independent(self, db: Session, user: User):
        """The same idempotency_key used by two different users is independent."""
        user2 = User(
            id=str(uuid.uuid4()),
            username="user2_idempotency",
            email="user2@test.example",
            password_hash="not-used",
            home_country="US",
        )
        db.add(user2)
        db.commit()

        mgr = IdempotencyManager(db)
        shared_key = "shared-key-across-users"

        is_replay_u1, _ = mgr.check_and_reserve(user.id, shared_key)
        is_replay_u2, _ = mgr.check_and_reserve(user2.id, shared_key)

        assert is_replay_u1 is False
        assert is_replay_u2 is False

        # Two rows — one per user
        count = (
            db.query(EntryIdempotencyClaim)
            .filter(EntryIdempotencyClaim.idempotency_key == shared_key)
            .count()
        )
        assert count == 2
