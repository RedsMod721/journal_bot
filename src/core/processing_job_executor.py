"""
Processing job executor with retry logic.

Implements Section 11.8 (Failure Handling + Retries) from architecture,
specifically 11.8.3 (Retries, backoff, and breaker interaction).

Backoff schedule (exponential with jitter, cap 5000 ms):
    attempt 1 → 1000 ms base + jitter
    attempt 2 → 2000 ms base + jitter
    (cap applied before jitter is added)

Circuit breaker interaction:
    - Every failed execution increments breaker counters automatically via
      CircuitBreaker.check_and_execute().
    - When breaker is OPEN, CircuitBreakerOpenError is raised immediately and
      the retry loop is short-circuited (no further attempts).

Validation / non-retriable errors:
    - Callers may pass ``non_retriable`` exception types; those skip remaining
      retries and finalize the job as failed immediately.
"""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.exc import SQLAlchemyError

from src.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from src.db.models.processing import ProcessingJob, ProcessingJobAttempt
from src.db.models.processing_distributed import ProcessingJobClaim
from src.jobs.processing_job_service import (
    AttemptStatus,
    ExecutorType,
    ProcessingJobService,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backoff constants (Section 11.8.3)
# ---------------------------------------------------------------------------

_BASE_BACKOFF_MS = 1000          # 1 s per retry step
_MAX_BACKOFF_MS = 5_000          # hard cap
_JITTER_MS = 500                 # uniform random [0, JITTER_MS)


def _backoff_seconds(attempt_num: int) -> float:
    """Return sleep duration in seconds for the given retry number (0 = first retry)."""
    base_ms = min(_MAX_BACKOFF_MS, _BASE_BACKOFF_MS * (2 ** attempt_num))
    jitter_ms = random.randint(0, _JITTER_MS)
    return (base_ms + jitter_ms) / 1000.0


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class ProcessingJobExecutor:
    """Execute processing jobs with retry logic and circuit breaker integration.

    Responsibilities:
    - Enforce max_attempts cap (default 3, per Section 11.8.3).
    - Apply exponential backoff with jitter (cap 5000 ms) between retries.
    - Short-circuit on CircuitBreakerOpenError (no retry, finalize failed).
    - Delegate attempt + job lifecycle to ProcessingJobService so audit rows
      are consistent with the rest of the system.
    - Expose structured ``[PJE:]`` log records for easy log-aggregator queries.

    Usage::

        executor = ProcessingJobExecutor(
            job_service=svc,
            circuit_breaker=cb,
            max_attempts=3,
        )
        result = executor.execute_with_retry(
            job=job,
            claim=claim,
            executor_func=run_ai_step,
            executor_type="server_local",
        )
    """

    def __init__(
        self,
        job_service: ProcessingJobService,
        circuit_breaker: CircuitBreaker,
        max_attempts: int = 3,
    ) -> None:
        self.job_service = job_service
        self.circuit_breaker = circuit_breaker
        self.max_attempts = max_attempts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_with_retry(
        self,
        job: ProcessingJob,
        claim: ProcessingJobClaim,
        executor_func: Callable[..., Any],
        *args: Any,
        executor_type: ExecutorType = "server_local",
        non_retriable: tuple[type[Exception], ...] = (),
        **kwargs: Any,
    ) -> Any:
        """Execute *executor_func* through the circuit breaker with retry logic.

        Args:
            job:           Active ``ProcessingJob`` row (status must be ``in_progress``).
            claim:         Matching ``ProcessingJobClaim`` (released on finalization).
            executor_func: Callable to invoke (e.g. an AI pipeline step).
            *args:         Positional arguments forwarded to *executor_func*.
            executor_type: Recorded on each attempt row (default ``server_local``).
            non_retriable: Exception types that skip retries (e.g. validation errors).
            **kwargs:      Keyword arguments forwarded to *executor_func*.

        Returns:
            The return value of *executor_func* on success.

        Raises:
            CircuitBreakerOpenError: Breaker is OPEN — fast-fail, no retry.
            Exception:               Final exception after max attempts exhausted,
                                     or a non-retriable exception on the first failure.
        """
        scope_key = f"ai:{job.step_name}"
        job_ctx = {
            "job_id": job.id,
            "user_id": job.user_id,
            "entry_id": job.entry_id,
            "step_name": job.step_name,
        }

        logger.info(
            "[PJE:pipeline] Starting execution job_id=%s step=%s max_attempts=%d",
            job.id,
            job.step_name,
            self.max_attempts,
            extra={"job_ctx": job_ctx},
        )

        last_exc: Exception | None = None

        for attempt_num in range(self.max_attempts):
            # ----------------------------------------------------------
            # Exponential backoff (skip on first attempt)
            # ----------------------------------------------------------
            if attempt_num > 0:
                delay = _backoff_seconds(attempt_num - 1)
                logger.info(
                    "[PJE:pipeline] Backoff before retry attempt=%d delay_s=%.3f "
                    "job_id=%s step=%s",
                    attempt_num + 1,
                    delay,
                    job.id,
                    job.step_name,
                    extra={"job_ctx": job_ctx},
                )
                time.sleep(delay)

            # ----------------------------------------------------------
            # Open attempt row (immutable audit log)
            # ----------------------------------------------------------
            attempt = self.job_service.start_attempt(
                job=job,
                executor_type=executor_type,
            )

            logger.info(
                "[PJE:pipeline] Attempt #%d/%d starting job_id=%s step=%s "
                "attempt_row_id=%s",
                attempt_num + 1,
                self.max_attempts,
                job.id,
                job.step_name,
                attempt.id,
                extra={"job_ctx": job_ctx},
            )

            # ----------------------------------------------------------
            # Execute through circuit breaker
            # ----------------------------------------------------------
            start_time = datetime.now(timezone.utc)

            try:
                result = self.circuit_breaker.check_and_execute(
                    scope_key, executor_func, *args, **kwargs
                )

                duration_ms = _elapsed_ms(start_time)

                self.job_service.finish_attempt(
                    attempt=attempt,
                    status="succeeded",
                    duration_ms=duration_ms,
                    payload=result,
                )
                self.job_service.finalize_job(
                    job=job,
                    claim=claim,
                    status="succeeded",
                    final_payload=result,
                )

                logger.info(
                    "[PJE:pipeline] Execution succeeded job_id=%s step=%s "
                    "attempt=#%d duration_ms=%d",
                    job.id,
                    job.step_name,
                    attempt_num + 1,
                    duration_ms,
                    extra={"job_ctx": job_ctx},
                )
                return result

            except CircuitBreakerOpenError as exc:
                # Breaker is OPEN — Section 11.8.3: short-circuit immediately.
                duration_ms = _elapsed_ms(start_time)
                logger.error(
                    "[PJE:pipeline] Circuit breaker OPEN — aborting job_id=%s "
                    "step=%s scope=%s",
                    job.id,
                    job.step_name,
                    scope_key,
                    extra={"job_ctx": job_ctx},
                )
                self._fail_attempt(attempt, "CIRCUIT_BREAKER_OPEN", str(exc), duration_ms)
                self._fail_job(job, claim, "CIRCUIT_BREAKER_OPEN", str(exc))
                raise

            except non_retriable as exc:  # type: ignore[misc]
                # Validation / contract failure — non-retriable per 11.8.3.
                duration_ms = _elapsed_ms(start_time)
                error_code = type(exc).__name__
                logger.warning(
                    "[PJE:pipeline] Non-retriable error job_id=%s step=%s "
                    "error_code=%s: %s",
                    job.id,
                    job.step_name,
                    error_code,
                    exc,
                    extra={"job_ctx": job_ctx},
                )
                self._fail_attempt(attempt, error_code, str(exc), duration_ms)
                self._fail_job(job, claim, error_code, str(exc))
                raise

            except Exception as exc:
                duration_ms = _elapsed_ms(start_time)
                error_code = type(exc).__name__
                last_exc = exc

                logger.warning(
                    "[PJE:pipeline] Attempt #%d failed job_id=%s step=%s "
                    "error_code=%s: %s",
                    attempt_num + 1,
                    job.id,
                    job.step_name,
                    error_code,
                    exc,
                    extra={"job_ctx": job_ctx},
                )
                self._fail_attempt(attempt, error_code, str(exc), duration_ms)

                if attempt_num + 1 >= self.max_attempts:
                    logger.error(
                        "[PJE:pipeline] Max attempts exhausted job_id=%s step=%s "
                        "attempts=%d final_error=%s: %s",
                        job.id,
                        job.step_name,
                        self.max_attempts,
                        error_code,
                        exc,
                        extra={"job_ctx": job_ctx},
                    )
                    self._fail_job(job, claim, "MAX_ATTEMPTS_EXCEEDED", str(exc))
                    raise

        # Should be unreachable — max_attempts loop always raises or returns.
        raise RuntimeError(
            f"ProcessingJobExecutor loop completed without result for job {job.id}"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fail_attempt(
        self,
        attempt: ProcessingJobAttempt,
        error_code: str,
        error_message: str,
        duration_ms: int,
    ) -> None:
        """Seal attempt as failed, swallowing DB errors to avoid masking root cause."""
        try:
            self.job_service.finish_attempt(
                attempt=attempt,
                status="failed",
                duration_ms=duration_ms,
                error_code=error_code,
                error_message=error_message,
            )
        except SQLAlchemyError:
            logger.exception(
                "[PJE:pipeline] DB error recording failed attempt attempt_id=%s "
                "error_code=%s",
                attempt.id,
                error_code,
            )

    def _fail_job(
        self,
        job: ProcessingJob,
        claim: ProcessingJobClaim,
        error_code: str,
        error_message: str,
    ) -> None:
        """Finalize job as failed, swallowing DB errors to avoid masking root cause."""
        try:
            self.job_service.finalize_job(
                job=job,
                claim=claim,
                status="failed",
                error_code=error_code,
                error_message=error_message,
            )
        except SQLAlchemyError:
            logger.exception(
                "[PJE:pipeline] DB error finalizing failed job job_id=%s "
                "error_code=%s",
                job.id,
                error_code,
            )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _elapsed_ms(start: datetime) -> int:
    """Return milliseconds elapsed since *start* (UTC-aware)."""
    return int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
