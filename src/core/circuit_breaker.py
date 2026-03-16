"""
Circuit breaker implementation (Section 11.1.3).

States:
- CLOSED    → normal operation, requests pass through
- OPEN      → fast-fail, no AI calls
- HALF_OPEN → test requests allowed, monitoring recovery

Transitions:
- CLOSED    → OPEN      : failure_count >= failure_threshold (default 5)
- OPEN      → HALF_OPEN : timeout elapsed (default 60 s)
- HALF_OPEN → CLOSED    : success_count >= success_threshold (default 2)
- HALF_OPEN → OPEN      : any failure
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from src.db.models.circuit_breaker import CircuitBreakerState


class CircuitBreakerOpenError(Exception):
    """Raised when a call is rejected because the circuit breaker is OPEN."""


class CircuitBreaker:
    """DB-backed circuit breaker for AI execution protection."""

    def __init__(
        self,
        db: Session,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: int = 60,
    ) -> None:
        self.db = db
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timedelta(seconds=timeout_seconds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_and_execute(
        self,
        scope_key: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute *func* through the circuit breaker for *scope_key*.

        Raises:
            CircuitBreakerOpenError: circuit is OPEN and timeout hasn't elapsed.
        """
        state = self._get_or_create_state(scope_key)

        if state.state == "OPEN":
            now = datetime.now(timezone.utc)
            if state.next_attempt_at and now >= state.next_attempt_at.replace(
                tzinfo=timezone.utc
            ):
                self._transition_to_half_open(state)
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker OPEN for {scope_key!r}, "
                    f"next attempt at {state.next_attempt_at}"
                )

        try:
            result = func(*args, **kwargs)
            self._record_success(state)
            return result
        except Exception:
            self._record_failure(state)
            raise

    def get_state(self, scope_key: str) -> str:
        """Return current state string for *scope_key* ('CLOSED' if unknown)."""
        row = (
            self.db.query(CircuitBreakerState)
            .filter(CircuitBreakerState.scope_key == scope_key)
            .first()
        )
        return row.state if row else "CLOSED"

    def reset(self, scope_key: str) -> None:
        """Force-reset circuit breaker to CLOSED (admin / test use)."""
        state = self._get_or_create_state(scope_key)
        now = datetime.now(timezone.utc)
        state.state = "CLOSED"
        state.failure_count = 0
        state.success_count = 0
        state.opened_at = None
        state.half_opened_at = None
        state.next_attempt_at = None
        state.updated_at = now
        self.db.flush()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _get_or_create_state(self, scope_key: str) -> CircuitBreakerState:
        state = (
            self.db.query(CircuitBreakerState)
            .filter(CircuitBreakerState.scope_key == scope_key)
            .first()
        )
        if not state:
            now = datetime.now(timezone.utc)
            state = CircuitBreakerState(
                scope_key=scope_key,
                state="CLOSED",
                failure_count=0,
                success_count=0,
                created_at=now,
                updated_at=now,
            )
            self.db.add(state)
            self.db.flush()
        return state

    def _record_success(self, state: CircuitBreakerState) -> None:
        now = datetime.now(timezone.utc)
        state.success_count += 1
        state.failure_count = 0
        state.last_success_at = now
        state.updated_at = now

        if state.state == "HALF_OPEN" and state.success_count >= self.success_threshold:
            state.state = "CLOSED"
            state.success_count = 0
            state.half_opened_at = None
            state.next_attempt_at = None

        self.db.flush()

    def _record_failure(self, state: CircuitBreakerState) -> None:
        now = datetime.now(timezone.utc)
        state.failure_count += 1
        state.success_count = 0
        state.last_failure_at = now
        state.updated_at = now

        if state.state == "CLOSED":
            if state.failure_count >= self.failure_threshold:
                self._transition_to_open(state, now)
        elif state.state == "HALF_OPEN":
            self._transition_to_open(state, now)

        self.db.flush()

    def _transition_to_open(self, state: CircuitBreakerState, now: datetime) -> None:
        state.state = "OPEN"
        state.opened_at = now
        state.next_attempt_at = now + self.timeout
        state.failure_count = 0
        state.success_count = 0

    def _transition_to_half_open(self, state: CircuitBreakerState) -> None:
        now = datetime.now(timezone.utc)
        state.state = "HALF_OPEN"
        state.half_opened_at = now
        state.failure_count = 0
        state.success_count = 0
        state.updated_at = now
        self.db.flush()
