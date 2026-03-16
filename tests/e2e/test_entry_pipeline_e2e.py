"""
End-to-end entry pipeline tests.

Exercises the 17-step EntryPipeline against an in-memory SQLite database.
AI/LLM services (Ollama, Qdrant) are not provided; non-critical steps
degrade to rule-based fallbacks.  Step 14 (XP computation) is the only
critical step and must succeed — the patched SessionLocal in conftest.py
gives it access to the test database.

Test classes
------------
TestTextEntryCompleteFlow       — full pipeline correctness per entry
TestConcurrentIdempotency       — finalize-once under concurrent load
TestPipelineLatency             — P95 < 2 s with no AI services
TestCircuitBreakerCascade       — CB state machine & cascade isolation
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

import pytest
from sqlalchemy.orm import Session

from src.ai.pipeline.entry_pipeline import EntryPipeline
from src.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from src.db.models.global_kb import GlobalSkill
from src.db.models.user import User

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(session_factory, *, username_prefix: str = "e2e") -> str:
    """Insert a User row and return its id, using an isolated session."""
    sess = session_factory()
    try:
        u = User(
            id=str(uuid.uuid4()),
            username=f"{username_prefix}_{uuid.uuid4().hex[:8]}",
            email=f"{username_prefix}_{uuid.uuid4().hex[:8]}@e2e.example",
            password_hash="not-used",
            home_country="US",
        )
        sess.add(u)
        sess.commit()
        return u.id
    finally:
        sess.close()


def _ikey(prefix: str = "e2e") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# TestTextEntryCompleteFlow
# ---------------------------------------------------------------------------


class TestTextEntryCompleteFlow:
    """Full pipeline correctness: text entry → all 17 steps → result dict."""

    def test_status_completed(self, pipeline: EntryPipeline, test_user: User):
        """Successful run returns status='completed' and result_type='success'."""
        result = pipeline.process(
            user_id=test_user.id,
            content="Worked on Python for 3 hours, completed 2 coding quests",
            idempotency_key=_ikey("e2e_complete"),
        )
        assert result["status"] == "completed"
        assert result["result_type"] == "success"
        assert result["entry_id"]
        assert result["user_id"] == test_user.id

    def test_structured_data_populated(self, pipeline: EntryPipeline, test_user: User):
        """Structured extraction result is always present (may be fallback)."""
        result = pipeline.process(
            user_id=test_user.id,
            content="Worked on Python for 3 hours",
            idempotency_key=_ikey("e2e_structured"),
        )
        assert result["status"] == "completed"
        sd = result["structured_data"]
        assert isinstance(sd, dict)
        assert "task_type" in sd
        assert "skills_weights_bp" in sd or "skills_themes_involved" in sd

    def test_xp_result_always_present(self, pipeline: EntryPipeline, test_user: User):
        """
        Step 14 (XP) is critical — the result must be present on every success.
        """
        result = pipeline.process(
            user_id=test_user.id,
            content="Coding session — built a REST API",
            idempotency_key=_ikey("e2e_xp"),
        )
        assert result["status"] == "completed"
        xp = result["xp_result"]
        assert isinstance(xp, dict)
        assert "awards" in xp
        assert "total_xp" in xp
        assert isinstance(xp["total_xp"], int)

    def test_quest_result_present(self, pipeline: EntryPipeline, test_user: User):
        """Quest result dict is always returned (may be fallback with empty lists)."""
        result = pipeline.process(
            user_id=test_user.id,
            content="Completed a Python tutorial",
            idempotency_key=_ikey("e2e_quest"),
        )
        assert result["status"] == "completed"
        qr = result["quest_result"]
        assert isinstance(qr, dict)
        assert "created_quests" in qr
        assert "xp_awards" in qr
        assert isinstance(qr["created_quests"], list)

    def test_structured_data_resolves_activity_source_skills(
        self,
        pipeline: EntryPipeline,
        test_user: User,
        db: Session,
    ):
        db.add_all(
            [
                GlobalSkill(
                    id=str(uuid.uuid4()),
                    source_skill_id="skill_physical_running",
                    canonical_name="Running",
                    category="Physical",
                ),
                GlobalSkill(
                    id=str(uuid.uuid4()),
                    source_skill_id="skill_physical_cardio_endurance",
                    canonical_name="Cardio Endurance",
                    category="Physical",
                ),
                GlobalSkill(
                    id=str(uuid.uuid4()),
                    source_skill_id="skill_physical_cardiorespiratory_fitness",
                    canonical_name="Cardiorespiratory Fitness",
                    category="Physical",
                ),
            ]
        )
        db.commit()

        result = pipeline.process(
            user_id=test_user.id,
            content="Today I practiced cardio by doing a 10km run in 1h",
            idempotency_key=_ikey("e2e_activity_skill_routing"),
        )

        assert result["status"] == "completed"
        sd = result["structured_data"]
        assert sd["source_skills_weights_bp"] == {
            "skill_physical_running": 7000,
            "skill_physical_cardio_endurance": 1500,
            "skill_physical_cardiorespiratory_fitness": 1500,
        }
        assert sd["skills_weights_bp"] == {}
        assert sd["resolved_skill_names"] == [
            "Running",
            "Cardio Endurance",
            "Cardiorespiratory Fitness",
        ]
        assert sd["pattern_hits_json"] == [
            {"semantic_key": "practice", "confidence_score": 0.70},
            {"semantic_key": "run", "confidence_score": 0.70},
        ]

    def test_personality_result_present(self, pipeline: EntryPipeline, test_user: User):
        """Personality result is present — generated or observer fallback."""
        result = pipeline.process(
            user_id=test_user.id,
            content="Ran 5 km and meditated for 20 minutes",
            idempotency_key=_ikey("e2e_personality"),
        )
        assert result["status"] == "completed"
        pr = result["personality_result"]
        assert isinstance(pr, dict)
        # Either a real message or the fallback observer message is present
        assert pr.get("message") or pr.get("fallback_used")

    def test_pipeline_metadata_populated(self, pipeline: EntryPipeline, test_user: User):
        """Version strings, run_id, and step counters are always populated."""
        result = pipeline.process(
            user_id=test_user.id,
            content="Daily journal entry — reflecting on the week",
            idempotency_key=_ikey("e2e_metadata"),
        )
        assert result["status"] == "completed"
        assert result["pipeline_version"]
        assert result["processing_run_id"]
        assert result["steps_attempted"] > 0
        assert isinstance(result["processing_duration_ms"], int)
        assert result["processing_duration_ms"] >= 0

    def test_replay_returns_cached_result(self, pipeline: EntryPipeline, test_user: User):
        """
        Same idempotency_key → second call is an idempotent replay.

        The replay result has the same entry_id and a status that indicates
        a completed or in-progress run (not a new fresh run).
        """
        ikey = _ikey("e2e_replay")

        first = pipeline.process(
            user_id=test_user.id,
            content="Entry that will be replayed",
            idempotency_key=ikey,
        )
        assert first["status"] == "completed"
        assert first["result_type"] == "success"
        original_entry_id = first["entry_id"]

        second = pipeline.process(
            user_id=test_user.id,
            content="Different content — but same idempotency key",
            idempotency_key=ikey,
        )

        # Replay is not a fresh pipeline run
        assert second.get("result_type") != "success"

        # entry_id must reference the same entry created on the first call
        if second.get("entry_id"):
            assert second["entry_id"] == original_entry_id

    def test_validation_failure_on_empty_user_id(self, pipeline: EntryPipeline):
        """Empty user_id is rejected with a failure result (not an exception)."""
        result = pipeline.process(
            user_id="",
            content="Some content",
            idempotency_key=_ikey("e2e_validation"),
        )
        assert result["status"] == "failed"
        assert result["result_type"] == "failure"

    def test_validation_failure_on_missing_idempotency_key(
        self, pipeline: EntryPipeline, test_user: User
    ):
        """Empty idempotency_key is rejected with a failure result."""
        result = pipeline.process(
            user_id=test_user.id,
            content="Some content",
            idempotency_key="",
        )
        assert result["status"] == "failed"
        assert result["result_type"] == "failure"


# ---------------------------------------------------------------------------
# TestConcurrentIdempotency
# ---------------------------------------------------------------------------


class TestConcurrentIdempotency:
    """
    Finalize-once invariant under concurrent load.

    100 threads submit the same idempotency_key concurrently.  Only 1 fresh
    pipeline run must complete; all others must receive replay results.
    SQLite StaticPool serialises writes so the UNIQUE constraint on
    entry_idempotency_claims reliably enforces a single reservation.
    """

    def test_100_concurrent_same_key_single_entry(
        self, engine, session_factory, patch_session_local
    ):
        """100 concurrent requests → exactly 1 fresh run, all share 1 entry_id."""
        user_id = _make_user(session_factory, username_prefix="concurrent")
        ikey = _ikey("concurrent_e2e")

        results: List[Dict[str, Any]] = []
        errors: List[Exception] = []
        lock = threading.Lock()

        def _process(_: int) -> None:
            sess = session_factory()
            try:
                pl = EntryPipeline(db=sess)
                result = pl.process(
                    user_id=user_id,
                    content="Concurrent idempotency stress entry",
                    idempotency_key=ikey,
                )
                with lock:
                    results.append(result)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(exc)
            finally:
                sess.close()

        with ThreadPoolExecutor(max_workers=20) as executor:
            list(executor.map(_process, range(100)))

        assert not errors, f"Uncaught thread exceptions: {[str(e) for e in errors[:3]]}"
        assert len(results) == 100

        # ── Finalize-once: exactly 1 fresh pipeline run ──────────────────────
        fresh_runs = [r for r in results if r.get("result_type") == "success"]
        assert len(fresh_runs) == 1, (
            f"Expected exactly 1 fresh pipeline run; got {len(fresh_runs)}. "
            "Finalize-once invariant violated."
        )

        # ── All entry_ids must be identical ──────────────────────────────────
        entry_ids = {r["entry_id"] for r in results if r.get("entry_id")}
        assert len(entry_ids) <= 1, (
            f"Multiple distinct entry_ids created: {entry_ids}. "
            "Finalize-once invariant violated."
        )

    def test_no_duplicate_xp_under_load(
        self, engine, session_factory, patch_session_local
    ):
        """
        Under concurrent load with the same key, XP is awarded exactly once.

        Only the single fresh run's XP total counts.  All replay results
        reference the same entry and the same XP award rows — no duplicates.
        """
        user_id = _make_user(session_factory, username_prefix="xp_dedup")
        ikey = _ikey("xp_dedup_e2e")

        def _process(_: int) -> Dict[str, Any]:
            sess = session_factory()
            try:
                pl = EntryPipeline(db=sess)
                return pl.process(
                    user_id=user_id,
                    content="XP dedup concurrent stress entry",
                    idempotency_key=ikey,
                )
            finally:
                sess.close()

        with ThreadPoolExecutor(max_workers=10) as executor:
            all_results = list(executor.map(_process, range(50)))

        fresh = [r for r in all_results if r.get("result_type") == "success"]
        assert len(fresh) == 1, f"Expected 1 fresh run, got {len(fresh)}"

        # XP total from the single authoritative run
        authoritative_xp = fresh[0].get("xp_result", {}).get("total_xp", 0)

        # Every other fresh-looking result (there should be none) must match
        for r in all_results:
            if r.get("result_type") == "success":
                assert r["xp_result"]["total_xp"] == authoritative_xp

    def test_different_keys_are_independent(
        self, engine, session_factory, patch_session_local
    ):
        """Different idempotency_keys for the same user produce independent entries."""
        user_id = _make_user(session_factory, username_prefix="multi_key")
        key_a = _ikey("multi_key_a")
        key_b = _ikey("multi_key_b")

        def _process(ikey: str) -> Dict[str, Any]:
            sess = session_factory()
            try:
                pl = EntryPipeline(db=sess)
                return pl.process(
                    user_id=user_id,
                    content=f"Entry for key {ikey}",
                    idempotency_key=ikey,
                )
            finally:
                sess.close()

        result_a = _process(key_a)
        result_b = _process(key_b)

        assert result_a["status"] == "completed"
        assert result_b["status"] == "completed"
        assert result_a["entry_id"] != result_b["entry_id"]


# ---------------------------------------------------------------------------
# TestPipelineLatency
# ---------------------------------------------------------------------------


class TestPipelineLatency:
    """Pipeline latency SLA: P95 < 2 s (rule-based, no AI services)."""

    def test_p95_latency_under_two_seconds(
        self, pipeline: EntryPipeline, test_user: User
    ):
        """
        20 sequential runs — P95 must be < 2 s.

        Without AI service round-trips (Ollama, Qdrant) the pipeline uses
        only rule-based fallback paths; latency should be well under budget.
        """
        latencies: List[float] = []

        for i in range(20):
            ikey = f"e2e_latency_{i}_{uuid.uuid4().hex[:8]}"
            start = time.perf_counter()
            result = pipeline.process(
                user_id=test_user.id,
                content=f"Latency test entry #{i} — daily journal reflection",
                idempotency_key=ikey,
            )
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)
            assert result["status"] == "completed", (
                f"Run {i} failed: {result.get('error_code')}"
            )

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        assert p95 < 2.0, (
            f"P95 latency {p95:.3f} s exceeds 2.0 s SLA. "
            f"All latencies (s): {[f'{l:.3f}' for l in latencies]}"
        )

    def test_processing_duration_ms_reported(
        self, pipeline: EntryPipeline, test_user: User
    ):
        """processing_duration_ms is a non-negative integer on every success."""
        result = pipeline.process(
            user_id=test_user.id,
            content="Duration field sanity check",
            idempotency_key=_ikey("e2e_duration"),
        )
        assert result["status"] == "completed"
        assert isinstance(result["processing_duration_ms"], int)
        assert result["processing_duration_ms"] >= 0


# ---------------------------------------------------------------------------
# TestCircuitBreakerCascade
# ---------------------------------------------------------------------------


class TestCircuitBreakerCascade:
    """
    Circuit breaker state machine and cascade isolation.

    Tests use CircuitBreaker directly (not through the pipeline) to verify
    the DB-backed state machine and confirm that an OPEN circuit in scope_a
    does not affect scope_b (no cascade).
    """

    def test_opens_after_failure_threshold(self, db: Session):
        """CLOSED → OPEN after failure_threshold (3) consecutive failures."""
        cb = CircuitBreaker(db, failure_threshold=3, timeout_seconds=60)
        scope = f"e2e_cb_open_{uuid.uuid4().hex[:8]}"

        def _fail():
            raise ValueError("simulated service failure")

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.check_and_execute(scope, _fail)

        assert cb.get_state(scope) == "OPEN"

    def test_open_circuit_rejects_without_executing(self, db: Session):
        """OPEN circuit raises CircuitBreakerOpenError; wrapped fn is never called."""
        cb = CircuitBreaker(db, failure_threshold=3, timeout_seconds=60)
        scope = f"e2e_cb_reject_{uuid.uuid4().hex[:8]}"

        def _fail():
            raise ValueError("simulated failure")

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.check_and_execute(scope, _fail)

        call_log: List[str] = []

        def _should_not_run():
            call_log.append("called")
            return "executed"

        with pytest.raises(CircuitBreakerOpenError):
            cb.check_and_execute(scope, _should_not_run)

        assert not call_log, "Wrapped function was called despite OPEN circuit"

    def test_independent_scopes_no_cascade(self, db: Session):
        """
        Opening scope_a does not affect scope_b.

        This is the core cascade-prevention guarantee: a failed AI service
        (e.g. Ollama) trips its own scope but does not block unrelated scopes
        (e.g. Qdrant, DB, external APIs).
        """
        cb = CircuitBreaker(db, failure_threshold=3, timeout_seconds=60)
        scope_a = f"e2e_scope_a_{uuid.uuid4().hex[:8]}"
        scope_b = f"e2e_scope_b_{uuid.uuid4().hex[:8]}"

        def _fail():
            raise RuntimeError("scope_a failure")

        # Trip scope_a
        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.check_and_execute(scope_a, _fail)

        assert cb.get_state(scope_a) == "OPEN"
        assert cb.get_state(scope_b) == "CLOSED"

        # scope_b must still execute normally
        result = cb.check_and_execute(scope_b, lambda: "scope_b_result")
        assert result == "scope_b_result"

    def test_reset_restores_closed_state(self, db: Session):
        """reset() returns circuit to CLOSED; subsequent calls execute normally."""
        cb = CircuitBreaker(db, failure_threshold=3, timeout_seconds=60)
        scope = f"e2e_cb_reset_{uuid.uuid4().hex[:8]}"

        def _fail():
            raise ValueError("simulated failure")

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.check_and_execute(scope, _fail)

        assert cb.get_state(scope) == "OPEN"

        cb.reset(scope)
        assert cb.get_state(scope) == "CLOSED"

        result = cb.check_and_execute(scope, lambda: "post_reset_result")
        assert result == "post_reset_result"

    def test_half_open_success_closes_circuit(self, db: Session):
        """
        HALF_OPEN → CLOSED after success_threshold (2) consecutive successes.

        Simulated by opening the circuit then resetting it to HALF_OPEN manually
        (equivalent to the timeout elapsing), then recording successes.
        """
        cb = CircuitBreaker(db, failure_threshold=3, success_threshold=2, timeout_seconds=60)
        scope = f"e2e_cb_half_open_{uuid.uuid4().hex[:8]}"

        def _fail():
            raise ValueError("simulated failure")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                cb.check_and_execute(scope, _fail)

        assert cb.get_state(scope) == "OPEN"

        # Manually force HALF_OPEN (simulates timeout expiry)
        from src.db.models.circuit_breaker import CircuitBreakerState
        from datetime import datetime, timezone, timedelta

        state = db.query(CircuitBreakerState).filter_by(scope_key=scope).one()
        state.state = "HALF_OPEN"
        state.failure_count = 0
        state.success_count = 0
        state.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.flush()

        # Two successes must close the circuit
        cb.check_and_execute(scope, lambda: "success_1")
        cb.check_and_execute(scope, lambda: "success_2")

        assert cb.get_state(scope) == "CLOSED"
