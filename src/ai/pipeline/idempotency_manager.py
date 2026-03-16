"""
Idempotency manager for the entry pipeline.

Implements Section 13.5.2 (Finalize-Once) and the ingestion idempotency
model from COMPLETE_ARCHITECTURE.md.

Claim lifecycle
---------------
    reserved → in_progress → completed
                           → failed_retryable   (allows retry)
                           → failed_terminal    (blocks retry)

Concurrency
-----------
UNIQUE(user_id, idempotency_key) on entry_idempotency_claims serializes
concurrent first-time requests at the DB layer.  The loser of a race
catches IntegrityError, rolls back, re-reads the winner's claim, and
returns the appropriate replay response.

Finalize-Once
-------------
The partial unique index uq_processing_jobs_one_success enforces one
succeeded ProcessingJob per (user_id, entry_id, step_name).  can_finalize()
provides an early-exit application-level check backed by that index.

Logging namespaces
------------------
[idempotency:check]     Lookup / reservation decisions
[idempotency:lifecycle] State transitions (in_progress, complete, fail)
[idempotency:race]      Concurrent reservation events
[idempotency:error]     Non-fatal write failures
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple
import uuid

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from src.db.models.processing import EntryIdempotencyClaim

logger = logging.getLogger(__name__)

_RESULT_SCHEMA_VERSION = "1"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IdempotencyManager:
    """
    Manage idempotency claims for the entry pipeline.

    Each instance is bound to a single SQLAlchemy Session.  The caller
    is responsible for managing the session lifecycle.

    Replay semantics
    ----------------
    completed claim       → (True, result_pointer payload)
    in_progress/reserved  → (True, {status: in_progress, ...})
    failed_terminal       → (True, {status: failed_terminal, error_code: ...})
    failed_retryable      → (False, None)  — retry allowed
    no claim found        → INSERT reserved claim, return (False, None)
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Primary check / reservation
    # ------------------------------------------------------------------

    def check_and_reserve(
        self,
        user_id: str,
        idempotency_key: str,
    ) -> Tuple[bool, Optional[dict]]:
        """
        Check for an existing claim and reserve a new one if none exists.

        Commits the reservation immediately so it is visible to concurrent
        requests before Tx A begins.

        Returns:
            (is_replay, cached_result_or_none)
        """
        existing = self._find_claim(user_id, idempotency_key)
        if existing is not None:
            return self._handle_existing_claim(existing)

        # No existing claim — atomically reserve one.
        # If two requests race, only one INSERT will succeed; the loser
        # catches IntegrityError and re-reads the winner's claim.
        claim_id = str(uuid.uuid4())
        now = _now()
        claim = EntryIdempotencyClaim(
            id=claim_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            status="reserved",
            claimed_at=now,
            updated_at=now,
        )
        try:
            self.db.add(claim)
            self.db.commit()
        except (IntegrityError, SQLAlchemyError) as exc:
            # Catch both IntegrityError (standard) and the broader SQLAlchemyError
            # because some DB drivers (e.g. SQLite under concurrent StaticPool load)
            # surface UNIQUE violations as DatabaseError rather than IntegrityError.
            self.db.rollback()
            if "UNIQUE" not in str(exc) and not isinstance(exc, IntegrityError):
                # Non-uniqueness DB error — re-raise, do not silently swallow.
                raise
            logger.info(
                "[idempotency:race] Reservation race — re-reading winner's claim "
                "user=%s key=%s",
                user_id,
                idempotency_key,
            )
            existing = self._find_claim(user_id, idempotency_key)
            if existing is not None:
                return self._handle_existing_claim(existing)
            # Very unlikely (winner was immediately deleted); allow new run.
            logger.warning(
                "[idempotency:race] Race claim disappeared; allowing new run "
                "user=%s key=%s",
                user_id,
                idempotency_key,
            )
            return False, None

        logger.info(
            "[idempotency:check] Reserved new claim id=%s user=%s key=%s",
            claim_id,
            user_id,
            idempotency_key,
        )
        return False, None

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def advance_to_in_progress(
        self,
        user_id: str,
        idempotency_key: str,
        entry_id: str,
        job_id: str,
        processing_run_id: str,
    ) -> None:
        """
        Advance claim from reserved → in_progress after Tx A commits.

        Called immediately after Tx A so that polling clients receive a
        meaningful status before processing finishes.
        """
        claim = self._find_claim(user_id, idempotency_key)
        if claim is None:
            logger.warning(
                "[idempotency:lifecycle] advance_to_in_progress: claim not found "
                "user=%s key=%s — skipping",
                user_id,
                idempotency_key,
            )
            return

        now = _now()
        claim.status = "in_progress"
        claim.entry_id = entry_id
        claim.processing_job_id = job_id
        claim.processing_run_id = processing_run_id
        claim.updated_at = now
        try:
            self.db.commit()
            logger.info(
                "[idempotency:lifecycle] Claim → in_progress id=%s entry=%s job=%s",
                claim.id,
                entry_id,
                job_id,
            )
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception(
                "[idempotency:error] Failed to advance claim to in_progress "
                "user=%s key=%s",
                user_id,
                idempotency_key,
            )

    def complete(
        self,
        user_id: str,
        idempotency_key: str,
        entry_id: str,
        job_id: str,
        processing_run_id: str,
    ) -> None:
        """
        Mark claim completed after Tx B commits.

        Stores result_pointer_json so future replays return the cached
        result without re-running the pipeline.

        result_pointer_json schema (schema_version 1):
            {
                schema_version: "1",
                job_id: str,
                entry_id: str,
                processing_run_id: str,
                status: "completed",
                poll_path: "/api/v1/entries/{entry_id}/status"
            }
        """
        claim = self._find_claim(user_id, idempotency_key)
        if claim is None:
            logger.warning(
                "[idempotency:lifecycle] complete: claim not found "
                "user=%s key=%s — skipping",
                user_id,
                idempotency_key,
            )
            return

        result_pointer = {
            "schema_version": _RESULT_SCHEMA_VERSION,
            "job_id": job_id,
            "entry_id": entry_id,
            "processing_run_id": processing_run_id,
            "status": "completed",
            "poll_path": f"/api/v1/entries/{entry_id}/status",
        }
        now = _now()
        claim.status = "completed"
        claim.entry_id = entry_id
        claim.processing_job_id = job_id
        claim.processing_run_id = processing_run_id
        claim.result_pointer_json = json.dumps(result_pointer)
        claim.completed_at = now
        claim.updated_at = now
        try:
            self.db.commit()
            logger.info(
                "[idempotency:lifecycle] Claim → completed id=%s entry=%s job=%s",
                claim.id,
                entry_id,
                job_id,
            )
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception(
                "[idempotency:error] Failed to mark claim completed user=%s key=%s",
                user_id,
                idempotency_key,
            )

    def fail(
        self,
        user_id: str,
        idempotency_key: str,
        error_code: str,
        *,
        terminal: bool = False,
    ) -> None:
        """
        Mark claim failed.

        Args:
            terminal: True → failed_terminal (blocks retries).
                      False → failed_retryable (allows retries, default).
        """
        claim = self._find_claim(user_id, idempotency_key)
        if claim is None:
            logger.warning(
                "[idempotency:lifecycle] fail: claim not found user=%s key=%s — skipping",
                user_id,
                idempotency_key,
            )
            return

        new_status = "failed_terminal" if terminal else "failed_retryable"
        now = _now()
        claim.status = new_status
        claim.final_error_code = error_code
        claim.updated_at = now
        try:
            self.db.commit()
            logger.info(
                "[idempotency:lifecycle] Claim → %s id=%s error_code=%s",
                new_status,
                claim.id,
                error_code,
            )
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception(
                "[idempotency:error] Failed to mark claim %s user=%s key=%s",
                new_status,
                user_id,
                idempotency_key,
            )

    # ------------------------------------------------------------------
    # Finalize-once enforcement (application-level early exit)
    # ------------------------------------------------------------------

    def can_finalize(
        self,
        user_id: str,
        entry_id: str,
        step_name: str = "entry_pipeline",
    ) -> bool:
        """
        Return True if no succeeded ProcessingJob exists for this logical job.

        The partial unique index uq_processing_jobs_one_success is the
        authoritative guard in Tx B; this is an early-exit optimisation
        that avoids assembling Tx B when a winner already exists.
        """
        from src.db.models.processing import ProcessingJob

        existing = (
            self.db.query(ProcessingJob)
            .filter(
                ProcessingJob.user_id == user_id,
                ProcessingJob.entry_id == entry_id,
                ProcessingJob.step_name == step_name,
                ProcessingJob.status == "succeeded",
            )
            .first()
        )
        return existing is None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_claim(
        self, user_id: str, idempotency_key: str
    ) -> Optional[EntryIdempotencyClaim]:
        return (
            self.db.query(EntryIdempotencyClaim)
            .filter(
                EntryIdempotencyClaim.user_id == user_id,
                EntryIdempotencyClaim.idempotency_key == idempotency_key,
            )
            .first()
        )

    def _handle_existing_claim(
        self, claim: EntryIdempotencyClaim
    ) -> Tuple[bool, Optional[dict]]:
        """Translate an existing claim into a (is_replay, result) tuple."""

        if claim.status == "completed":
            pointer = (
                json.loads(claim.result_pointer_json)
                if claim.result_pointer_json
                else {}
            )
            logger.info(
                "[idempotency:check] Replay completed claim id=%s entry=%s",
                claim.id,
                claim.entry_id,
            )
            return True, {
                "result_type": "replay",
                "status": "completed",
                "entry_id": claim.entry_id,
                "job_id": claim.processing_job_id,
                "processing_run_id": claim.processing_run_id,
                "result_pointer": pointer,
            }

        if claim.status in ("reserved", "in_progress"):
            logger.info(
                "[idempotency:check] In-progress replay claim id=%s status=%s",
                claim.id,
                claim.status,
            )
            return True, {
                "result_type": "replay",
                "status": "in_progress",
                "claim_id": claim.id,
                "entry_id": claim.entry_id,
                "job_id": claim.processing_job_id,
                "processing_run_id": claim.processing_run_id,
            }

        if claim.status == "failed_terminal":
            logger.info(
                "[idempotency:check] Terminal failure replay claim id=%s error=%s",
                claim.id,
                claim.final_error_code,
            )
            return True, {
                "result_type": "replay",
                "status": "failed_terminal",
                "claim_id": claim.id,
                "error_code": claim.final_error_code,
            }

        # failed_retryable — allow a new run
        logger.info(
            "[idempotency:check] Retryable failure claim id=%s — allowing new run",
            claim.id,
        )
        return False, None
