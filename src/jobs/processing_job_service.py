"""
Processing job lifecycle service.

Owns the full state machine for processing_jobs / processing_job_attempts /
processing_job_claims:

    claim_job()         — atomic acquire: insert claim + create job row
    start_attempt()     — open a new attempt row (immutable audit log)
    finish_attempt()    — seal the attempt with status + duration
    finalize_job()      — mark job succeeded / failed, drop the claim
    heartbeat()         — extend lease while work is in progress
    release_claim()     — explicit early release (e.g. on graceful shutdown)
    get_or_create_job() — idempotent job lookup for pipeline re-entry

Logging conventions
-------------------
Every method emits structured log records with a ``job_ctx`` dict so that
log aggregators can correlate across LLM/RAG/pipeline steps:

    logger.info("[PJS] ...", extra={"job_ctx": {...}})

Methods that touch LLM, RAG, or pipeline outputs emit additional records at
INFO or WARNING level so they are easy to grep:

    [PJS:llm]      — LLM-version snapshot recorded on the job row
    [PJS:rag]      — RAG payload hash captured in the attempt row
    [PJS:pipeline] — pipeline step state transitions
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Generator, Literal

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from src.db.models.processing import ProcessingJob, ProcessingJobAttempt
from src.db.models.processing_distributed import ProcessingJobClaim

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

JobStatus = Literal["in_progress", "succeeded", "failed"]
AttemptStatus = Literal["succeeded", "failed", "rejected", "timeout"]
OwnerKind = Literal["server_worker", "scheduler", "admin_recovery"]
ExecutorType = Literal["server_local", "trusted_node"]

# Default lease duration; callers may override per-step.
DEFAULT_LEASE_SECONDS = 300  # 5 min


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class JobClaimError(RuntimeError):
    """Raised when another worker already holds the lease for a logical job."""


class JobNotFoundError(LookupError):
    """Raised when a job_id / claim_id does not exist."""


class JobStateError(RuntimeError):
    """Raised when a state transition is illegal (e.g. finalising a succeeded job)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


def _payload_hash(data: Any) -> str | None:
    """SHA-256 hex digest of the JSON-serialised payload, or None if data is falsy."""
    if not data:
        return None
    try:
        raw = json.dumps(data, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()
    except Exception:
        logger.warning("[PJS] Failed to hash payload — skipping", exc_info=True)
        return None


def _job_ctx(
    job: ProcessingJob | None = None,
    *,
    user_id: str | None = None,
    entry_id: str | None = None,
    step_name: str | None = None,
    run_id: str | None = None,
) -> dict:
    """Build a structured log context dict from a job row or raw identifiers."""
    if job is not None:
        return {
            "job_id": job.id,
            "user_id": job.user_id,
            "entry_id": job.entry_id,
            "step_name": job.step_name,
            "run_id": job.processing_run_id,
            "status": job.status,
            "attempt_count": job.attempt_count,
        }
    return {
        "user_id": user_id,
        "entry_id": entry_id,
        "step_name": step_name,
        "run_id": run_id,
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ProcessingJobService:
    """Stateless service — pass a ``Session`` to every method.

    Designed to be instantiated once per request or per background task and
    shared across all pipeline steps in that scope.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Claim + job creation
    # ------------------------------------------------------------------

    def claim_job(
        self,
        *,
        user_id: str,
        entry_id: str,
        step_name: str,
        processing_run_id: str,
        owner_kind: OwnerKind,
        owner_id: str,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        pipeline_version: str | None = None,
        ai_version_snapshot: dict | None = None,
        prompt_version_snapshot: dict | None = None,
    ) -> tuple[ProcessingJob, ProcessingJobClaim]:
        """Atomically acquire a lease and create (or re-activate) a job row.

        Raises ``JobClaimError`` if another worker already holds the claim.

        [PJS:pipeline] logs the step transition to ``in_progress``.
        [PJS:llm]      logs AI/prompt version snapshots when provided.
        """
        ctx = _job_ctx(
            user_id=user_id,
            entry_id=entry_id,
            step_name=step_name,
            run_id=processing_run_id,
        )
        logger.info(
            "[PJS:pipeline] Claiming job for step=%s run=%s",
            step_name,
            processing_run_id,
            extra={"job_ctx": ctx},
        )

        now = _now()

        # ---- claim row (enforce one-active-worker) ----
        existing_claim = (
            self.db.query(ProcessingJobClaim)
            .filter_by(user_id=user_id, entry_id=entry_id, step_name=step_name)
            .first()
        )
        if existing_claim is not None:
            if existing_claim.lease_expires_at.replace(tzinfo=timezone.utc) > now:
                raise JobClaimError(
                    f"Step '{step_name}' for entry {entry_id} is already claimed by "
                    f"owner_kind={existing_claim.owner_kind} owner_id={existing_claim.owner_id} "
                    f"(lease expires {existing_claim.lease_expires_at.isoformat()})"
                )
            # Lease expired — evict stale claim
            logger.warning(
                "[PJS:pipeline] Evicting stale claim for step=%s (expired %s)",
                step_name,
                existing_claim.lease_expires_at.isoformat(),
                extra={"job_ctx": ctx},
            )
            self.db.delete(existing_claim)
            self.db.flush()

        claim = ProcessingJobClaim(
            id=_new_id(),
            user_id=user_id,
            entry_id=entry_id,
            step_name=step_name,
            owner_kind=owner_kind,
            owner_id=owner_id,
            lease_token=_new_id(),
            claimed_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            heartbeat_at=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(claim)

        # ---- job row (idempotent for the logical job key) ----
        job = (
            self.db.query(ProcessingJob)
            .filter_by(
                user_id=user_id,
                entry_id=entry_id,
                step_name=step_name,
                processing_run_id=processing_run_id,
            )
            .first()
        )
        if job is None:
            job = ProcessingJob(
                id=_new_id(),
                user_id=user_id,
                entry_id=entry_id,
                step_name=step_name,
                processing_run_id=processing_run_id,
                status="in_progress",
                attempt_count=0,
                pipeline_version=pipeline_version,
                ai_version_snapshot=(
                    json.dumps(ai_version_snapshot) if ai_version_snapshot else None
                ),
                prompt_version_snapshot=(
                    json.dumps(prompt_version_snapshot) if prompt_version_snapshot else None
                ),
                created_at=now,
                updated_at=now,
            )
            self.db.add(job)
            logger.info(
                "[PJS:pipeline] Created new job row job_id=%s step=%s",
                job.id,
                step_name,
                extra={"job_ctx": _job_ctx(job)},
            )
        else:
            # Re-use existing job — bump status back to in_progress
            if job.status == "succeeded":
                raise JobStateError(
                    f"Job {job.id} for step '{step_name}' already succeeded; "
                    "cannot re-claim."
                )
            job.status = "in_progress"
            job.updated_at = now
            logger.info(
                "[PJS:pipeline] Re-activated existing job_id=%s step=%s attempt=%d",
                job.id,
                step_name,
                job.attempt_count,
                extra={"job_ctx": _job_ctx(job)},
            )

        if ai_version_snapshot:
            logger.info(
                "[PJS:llm] AI version snapshot recorded: %s",
                list(ai_version_snapshot.keys()),
                extra={"job_ctx": _job_ctx(job)},
            )
        if prompt_version_snapshot:
            logger.info(
                "[PJS:llm] Prompt version snapshot recorded: %s",
                list(prompt_version_snapshot.keys()),
                extra={"job_ctx": _job_ctx(job)},
            )

        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise JobClaimError(
                f"Concurrent claim conflict for step '{step_name}': {exc}"
            ) from exc

        return job, claim

    # ------------------------------------------------------------------
    # Attempt lifecycle
    # ------------------------------------------------------------------

    def start_attempt(
        self,
        *,
        job: ProcessingJob,
        executor_type: ExecutorType,
        node_id: str | None = None,
    ) -> ProcessingJobAttempt:
        """Open a new immutable attempt row and increment attempt_count on the job.

        [PJS:pipeline] logs the attempt start.
        """
        now = _now()
        next_attempt_id = job.attempt_count + 1
        ctx = _job_ctx(job)

        logger.info(
            "[PJS:pipeline] Starting attempt #%d for job_id=%s step=%s executor=%s",
            next_attempt_id,
            job.id,
            job.step_name,
            executor_type,
            extra={"job_ctx": ctx},
        )

        attempt = ProcessingJobAttempt(
            id=_new_id(),
            processing_job_id=job.id,
            attempt_id=next_attempt_id,
            attempted_at=now,
            executor_type=executor_type,
            node_id=node_id,
            status="failed",  # pessimistic default; overwritten by finish_attempt
        )
        self.db.add(attempt)

        job.attempt_count = next_attempt_id
        job.updated_at = now
        self.db.flush()

        if node_id:
            logger.info(
                "[PJS:pipeline] Attempt dispatched to trusted_node=%s",
                node_id,
                extra={"job_ctx": ctx},
            )

        return attempt

    def finish_attempt(
        self,
        *,
        attempt: ProcessingJobAttempt,
        status: AttemptStatus,
        duration_ms: int | None = None,
        payload: Any = None,
        error_code: str | None = None,
        error_message: str | None = None,
        rag_context: dict | None = None,
    ) -> None:
        """Seal an attempt row as immutable audit log.

        Args:
            payload:     Output payload for hashing (LLM response, pipeline result, etc.)
            rag_context: RAG retrieval context; triggers [PJS:rag] log when present.

        [PJS:rag]      logs RAG context hash if rag_context is provided.
        [PJS:pipeline] logs the attempt outcome.
        """
        ctx = _job_ctx(
            user_id=None,
            entry_id=None,
            step_name=None,
            run_id=None,
        )

        attempt.status = status
        attempt.duration_ms = duration_ms
        attempt.payload_hash = _payload_hash(payload)
        attempt.error_code = error_code
        attempt.error_message = error_message

        if rag_context:
            rag_hash = _payload_hash(rag_context)
            logger.info(
                "[PJS:rag] RAG context captured attempt_id=%s hash=%s hits=%d",
                attempt.id,
                rag_hash,
                rag_context.get("hit_count", len(rag_context)),
                extra={"job_ctx": {"attempt_id": attempt.id, "job_id": attempt.processing_job_id}},
            )

        logger.info(
            "[PJS:pipeline] Attempt %s finished status=%s duration_ms=%s payload_hash=%s",
            attempt.id,
            status,
            duration_ms,
            attempt.payload_hash,
            extra={"job_ctx": {"attempt_id": attempt.id, "job_id": attempt.processing_job_id}},
        )

        if status == "failed" and error_code:
            logger.warning(
                "[PJS:pipeline] Attempt failed error_code=%s: %s",
                error_code,
                error_message,
                extra={"job_ctx": {"attempt_id": attempt.id, "job_id": attempt.processing_job_id}},
            )

        self.db.flush()

    # ------------------------------------------------------------------
    # Job finalization
    # ------------------------------------------------------------------

    def finalize_job(
        self,
        *,
        job: ProcessingJob,
        claim: ProcessingJobClaim,
        status: Literal["succeeded", "failed"],
        final_payload: Any = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Transition job to terminal state and release the claim.

        [PJS:pipeline] logs the terminal transition.
        [PJS:llm]      logs when a succeeded payload hash is recorded (indicates
                       LLM output was committed to the job row).
        """
        if job.status not in ("in_progress",):
            raise JobStateError(
                f"Cannot finalize job {job.id}: current status is '{job.status}'"
            )

        now = _now()
        job.status = status
        job.finalized_at = now
        job.updated_at = now
        job.final_payload_hash = _payload_hash(final_payload)
        job.final_error_code = error_code
        job.final_error_message = error_message

        ctx = _job_ctx(job)

        if status == "succeeded":
            logger.info(
                "[PJS:pipeline] Job SUCCEEDED job_id=%s step=%s attempts=%d payload_hash=%s",
                job.id,
                job.step_name,
                job.attempt_count,
                job.final_payload_hash,
                extra={"job_ctx": ctx},
            )
            if job.final_payload_hash:
                logger.info(
                    "[PJS:llm] Final LLM/pipeline output committed to job job_id=%s hash=%s",
                    job.id,
                    job.final_payload_hash,
                    extra={"job_ctx": ctx},
                )
        else:
            logger.error(
                "[PJS:pipeline] Job FAILED job_id=%s step=%s attempts=%d error_code=%s: %s",
                job.id,
                job.step_name,
                job.attempt_count,
                error_code,
                error_message,
                extra={"job_ctx": ctx},
            )

        # Release the claim
        self.db.delete(claim)
        self.db.flush()

    # ------------------------------------------------------------------
    # Claim maintenance
    # ------------------------------------------------------------------

    def heartbeat(self, *, claim: ProcessingJobClaim, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> None:
        """Extend the claim lease and touch heartbeat_at."""
        now = _now()
        claim.heartbeat_at = now
        claim.lease_expires_at = now + timedelta(seconds=lease_seconds)
        claim.updated_at = now
        self.db.flush()
        logger.debug(
            "[PJS:pipeline] Heartbeat for claim_id=%s new_expiry=%s",
            claim.id,
            claim.lease_expires_at.isoformat(),
        )

    def release_claim(self, *, claim: ProcessingJobClaim) -> None:
        """Explicit early release without finalising the job (e.g. graceful shutdown)."""
        logger.info(
            "[PJS:pipeline] Releasing claim_id=%s for step=%s",
            claim.id,
            claim.step_name,
        )
        self.db.delete(claim)
        self.db.flush()

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def get_job(self, job_id: str) -> ProcessingJob:
        """Fetch a job by PK; raises ``JobNotFoundError`` if missing."""
        job = self.db.query(ProcessingJob).filter_by(id=job_id).first()
        if job is None:
            raise JobNotFoundError(f"ProcessingJob {job_id!r} not found")
        return job

    def get_or_create_job(
        self,
        *,
        user_id: str,
        entry_id: str,
        step_name: str,
        processing_run_id: str,
        pipeline_version: str | None = None,
    ) -> tuple[ProcessingJob, bool]:
        """Return (job, created).  Idempotent — safe to call multiple times.

        Does NOT acquire a claim.  Use ``claim_job`` when you need exclusive
        ownership.
        """
        job = (
            self.db.query(ProcessingJob)
            .filter_by(
                user_id=user_id,
                entry_id=entry_id,
                step_name=step_name,
                processing_run_id=processing_run_id,
            )
            .first()
        )
        if job is not None:
            logger.debug(
                "[PJS:pipeline] get_or_create_job: found existing job_id=%s status=%s",
                job.id,
                job.status,
                extra={"job_ctx": _job_ctx(job)},
            )
            return job, False

        now = _now()
        job = ProcessingJob(
            id=_new_id(),
            user_id=user_id,
            entry_id=entry_id,
            step_name=step_name,
            processing_run_id=processing_run_id,
            status="in_progress",
            attempt_count=0,
            pipeline_version=pipeline_version,
            created_at=now,
            updated_at=now,
        )
        self.db.add(job)
        self.db.flush()
        logger.info(
            "[PJS:pipeline] get_or_create_job: created job_id=%s step=%s",
            job.id,
            step_name,
            extra={"job_ctx": _job_ctx(job)},
        )
        return job, True

    def list_stale_claims(self, *, as_of: datetime | None = None) -> list[ProcessingJobClaim]:
        """Return all claims whose lease has expired."""
        cutoff = as_of or _now()
        return (
            self.db.query(ProcessingJobClaim)
            .filter(ProcessingJobClaim.lease_expires_at < cutoff)
            .all()
        )

    # ------------------------------------------------------------------
    # Context manager: full step lifecycle
    # ------------------------------------------------------------------

    @contextmanager
    def run_step(
        self,
        *,
        user_id: str,
        entry_id: str,
        step_name: str,
        processing_run_id: str,
        owner_kind: OwnerKind,
        owner_id: str,
        executor_type: ExecutorType = "server_local",
        node_id: str | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        pipeline_version: str | None = None,
        ai_version_snapshot: dict | None = None,
        prompt_version_snapshot: dict | None = None,
    ) -> Generator[tuple[ProcessingJob, ProcessingJobAttempt], None, None]:
        """Context manager that handles the full claim → attempt → finalize lifecycle.

        Usage::

            with svc.run_step(user_id=..., step_name="entry_pipeline", ...) as (job, attempt):
                result = run_llm_pipeline(...)
                svc.finish_attempt(attempt=attempt, status="succeeded", payload=result)

        On normal exit the job is finalized as succeeded (unless already finalized
        inside the ``with`` block).  On exception the job is finalized as failed.

        [PJS:pipeline] logs entry and exit of every step.
        """
        job, claim = self.claim_job(
            user_id=user_id,
            entry_id=entry_id,
            step_name=step_name,
            processing_run_id=processing_run_id,
            owner_kind=owner_kind,
            owner_id=owner_id,
            lease_seconds=lease_seconds,
            pipeline_version=pipeline_version,
            ai_version_snapshot=ai_version_snapshot,
            prompt_version_snapshot=prompt_version_snapshot,
        )
        attempt = self.start_attempt(
            job=job,
            executor_type=executor_type,
            node_id=node_id,
        )

        logger.info(
            "[PJS:pipeline] ENTER step=%s job_id=%s attempt=#%d",
            step_name,
            job.id,
            attempt.attempt_id,
            extra={"job_ctx": _job_ctx(job)},
        )

        try:
            yield job, attempt

            # Auto-finalize as succeeded if caller didn't already finalize
            if job.status == "in_progress":
                self.finish_attempt(attempt=attempt, status="succeeded")
                self.finalize_job(job=job, claim=claim, status="succeeded")

        except (JobClaimError, JobStateError):
            raise

        except Exception as exc:
            error_code = type(exc).__name__
            error_message = str(exc)
            logger.exception(
                "[PJS:pipeline] Unhandled exception in step=%s job_id=%s: %s",
                step_name,
                job.id,
                error_message,
                extra={"job_ctx": _job_ctx(job)},
            )
            try:
                if attempt.status == "failed":  # still at pessimistic default
                    self.finish_attempt(
                        attempt=attempt,
                        status="failed",
                        error_code=error_code,
                        error_message=error_message,
                    )
                if job.status == "in_progress":
                    self.finalize_job(
                        job=job,
                        claim=claim,
                        status="failed",
                        error_code=error_code,
                        error_message=error_message,
                    )
            except SQLAlchemyError:
                logger.exception(
                    "[PJS:pipeline] DB error while recording failure for job_id=%s",
                    job.id,
                )
                self.db.rollback()
            raise

        finally:
            logger.info(
                "[PJS:pipeline] EXIT step=%s job_id=%s final_status=%s",
                step_name,
                job.id,
                job.status,
                extra={"job_ctx": _job_ctx(job)},
            )
