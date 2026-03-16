"""
Processing job claim manager.

Implements Section 12.5 (Claims and Lease Lifecycle) from architecture.

Logging conventions
-------------------
Every method emits structured log records with a ``claim_ctx`` dict so that
log aggregators can correlate across LLM/RAG/pipeline steps:

    logger.info("[PCM] ...", extra={"claim_ctx": {...}})

Methods that touch LLM, RAG, or pipeline step transitions emit additional
tagged records so they are easy to grep:

    [PCM:claim]    — claim lifecycle (acquire, steal, release, cleanup)
    [PCM:pipeline] — pipeline step state transitions (step_name tagged)
    [PCM:llm]      — step is an LLM-backed pipeline step
    [PCM:rag]      — step involves RAG retrieval
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from src.db.models.processing_distributed import ProcessingJobClaim

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Step classification
# ---------------------------------------------------------------------------

# Steps that drive an LLM call inside the pipeline.
_LLM_STEPS: frozenset[str] = frozenset(
    {
        "entry_pipeline",
        "quest_generation",
        "insight_extraction",
        "personality_message_generation",
    }
)

# Steps that require RAG retrieval before or after the LLM call.
_RAG_STEPS: frozenset[str] = frozenset(
    {
        "personality_message_generation",
        "insight_extraction",
    }
)


def _is_llm_step(step_name: str) -> bool:
    return step_name in _LLM_STEPS


def _is_rag_step(step_name: str) -> bool:
    return step_name in _RAG_STEPS


# ---------------------------------------------------------------------------
# Structured log context
# ---------------------------------------------------------------------------


def _claim_ctx(
    claim: ProcessingJobClaim | None = None,
    *,
    user_id: str | None = None,
    entry_id: str | None = None,
    step_name: str | None = None,
    owner_kind: str | None = None,
    owner_id: str | None = None,
) -> dict:
    """Build a structured log context dict from a claim row or raw identifiers."""
    if claim is not None:
        return {
            "claim_id": claim.id,
            "user_id": claim.user_id,
            "entry_id": claim.entry_id,
            "step_name": claim.step_name,
            "owner_kind": claim.owner_kind,
            "owner_id": claim.owner_id,
            "lease_expires_at": claim.lease_expires_at.isoformat()
            if claim.lease_expires_at
            else None,
        }
    return {
        "user_id": user_id,
        "entry_id": entry_id,
        "step_name": step_name,
        "owner_kind": owner_kind,
        "owner_id": owner_id,
    }


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ClaimAlreadyHeldError(Exception):
    """Raised when claim is already held by another owner."""


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class ProcessingClaimManager:
    """
    Manage processing job claims with lease-based ownership.

    Provides:
    - Atomic claim acquisition
    - Lease expiry detection
    - Lease stealing
    - Heartbeat renewal
    """

    def __init__(
        self,
        db: Session,
        lease_duration_seconds: int = 30,
        heartbeat_interval_seconds: int = 10,
    ):
        self.db = db
        self.lease_duration = timedelta(seconds=lease_duration_seconds)
        self.heartbeat_interval = timedelta(seconds=heartbeat_interval_seconds)

    def acquire_claim(
        self,
        user_id: str,
        entry_id: str,
        step_name: str,
        owner_kind: str = "server_worker",
        owner_id: str | None = None,
    ) -> ProcessingJobClaim:
        """
        Atomically acquire claim for logical job.

        Algorithm (Section 12.5.1):
        1. Check if claim exists
        2. If exists and lease active → fail
        3. If exists and lease expired → steal
        4. If not exists → create

        Args:
            user_id: User ID
            entry_id: Entry ID (may be None for non-entry jobs)
            step_name: Step name
            owner_kind: 'server_worker', 'scheduler', or 'admin_recovery'
            owner_id: Owner identifier

        Returns:
            ProcessingJobClaim (acquired or stolen)

        Raises:
            ClaimAlreadyHeldError: Claim held by another owner
        """
        if owner_id is None:
            owner_id = f"server_{secrets.token_hex(8)}"

        now = datetime.now(timezone.utc)
        ctx = _claim_ctx(
            user_id=user_id,
            entry_id=entry_id,
            step_name=step_name,
            owner_kind=owner_kind,
            owner_id=owner_id,
        )

        logger.info(
            "[PCM:claim] Acquiring claim step=%s entry=%s owner=%s:%s",
            step_name,
            entry_id,
            owner_kind,
            owner_id,
            extra={"claim_ctx": ctx},
        )

        if _is_llm_step(step_name):
            logger.info(
                "[PCM:llm] Claim acquisition for LLM-backed step=%s entry=%s",
                step_name,
                entry_id,
                extra={"claim_ctx": ctx},
            )
        if _is_rag_step(step_name):
            logger.info(
                "[PCM:rag] Claim acquisition for RAG step=%s entry=%s",
                step_name,
                entry_id,
                extra={"claim_ctx": ctx},
            )

        existing_claim = (
            self.db.query(ProcessingJobClaim)
            .filter(
                ProcessingJobClaim.user_id == user_id,
                ProcessingJobClaim.entry_id == entry_id,
                ProcessingJobClaim.step_name == step_name,
            )
            .first()
        )

        if existing_claim:
            if existing_claim.lease_expires_at > now:
                logger.warning(
                    "[PCM:claim] Claim already held step=%s entry=%s "
                    "current_owner=%s:%s expires=%s",
                    step_name,
                    entry_id,
                    existing_claim.owner_kind,
                    existing_claim.owner_id,
                    existing_claim.lease_expires_at.isoformat(),
                    extra={"claim_ctx": _claim_ctx(existing_claim)},
                )
                raise ClaimAlreadyHeldError(
                    f"Claim held by {existing_claim.owner_kind}:{existing_claim.owner_id}, "
                    f"expires at {existing_claim.lease_expires_at}"
                )

            logger.warning(
                "[PCM:claim] Found expired claim step=%s entry=%s "
                "previous_owner=%s:%s expired=%s — stealing",
                step_name,
                entry_id,
                existing_claim.owner_kind,
                existing_claim.owner_id,
                existing_claim.lease_expires_at.isoformat(),
                extra={"claim_ctx": _claim_ctx(existing_claim)},
            )
            return self._steal_claim(existing_claim, owner_kind, owner_id, now)

        return self._create_claim(user_id, entry_id, step_name, owner_kind, owner_id, now)

    def _create_claim(
        self,
        user_id: str,
        entry_id: str,
        step_name: str,
        owner_kind: str,
        owner_id: str,
        now: datetime,
    ) -> ProcessingJobClaim:
        """
        Create new claim (atomic via unique constraint).

        Raises:
            ClaimAlreadyHeldError: Race condition — another process claimed first.
        """
        ctx = _claim_ctx(
            user_id=user_id,
            entry_id=entry_id,
            step_name=step_name,
            owner_kind=owner_kind,
            owner_id=owner_id,
        )

        claim = ProcessingJobClaim(
            id=str(uuid.uuid4()),
            user_id=user_id,
            entry_id=entry_id,
            step_name=step_name,
            owner_kind=owner_kind,
            owner_id=owner_id,
            lease_token=secrets.token_hex(16),
            claimed_at=now,
            lease_expires_at=now + self.lease_duration,
            heartbeat_at=now,
            created_at=now,
            updated_at=now,
        )

        try:
            self.db.add(claim)
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            logger.warning(
                "[PCM:claim] Race condition on create step=%s entry=%s — "
                "another process won the insert",
                step_name,
                entry_id,
                extra={"claim_ctx": ctx},
            )
            raise ClaimAlreadyHeldError(
                "Claim created by another process (race condition)"
            )
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception(
                "[PCM:claim] DB error creating claim step=%s entry=%s",
                step_name,
                entry_id,
                extra={"claim_ctx": ctx},
            )
            raise

        logger.info(
            "[PCM:claim] Created claim claim_id=%s step=%s entry=%s expires=%s",
            claim.id,
            step_name,
            entry_id,
            claim.lease_expires_at.isoformat(),
            extra={"claim_ctx": _claim_ctx(claim)},
        )
        logger.info(
            "[PCM:pipeline] Claim acquired for step=%s entry=%s claim_id=%s",
            step_name,
            entry_id,
            claim.id,
            extra={"claim_ctx": _claim_ctx(claim)},
        )

        if _is_llm_step(step_name):
            logger.info(
                "[PCM:llm] LLM step claim ready step=%s entry=%s claim_id=%s",
                step_name,
                entry_id,
                claim.id,
                extra={"claim_ctx": _claim_ctx(claim)},
            )
        if _is_rag_step(step_name):
            logger.info(
                "[PCM:rag] RAG step claim ready step=%s entry=%s claim_id=%s",
                step_name,
                entry_id,
                claim.id,
                extra={"claim_ctx": _claim_ctx(claim)},
            )

        return claim

    def _steal_claim(
        self,
        claim: ProcessingJobClaim,
        new_owner_kind: str,
        new_owner_id: str,
        now: datetime,
    ) -> ProcessingJobClaim:
        """Steal expired claim (rotate lease_token)."""
        previous_owner = f"{claim.owner_kind}:{claim.owner_id}"
        ctx = _claim_ctx(claim)

        claim.lease_token = secrets.token_hex(16)
        claim.owner_kind = new_owner_kind
        claim.owner_id = new_owner_id
        claim.claimed_at = now
        claim.lease_expires_at = now + self.lease_duration
        claim.heartbeat_at = now
        claim.updated_at = now

        try:
            self.db.flush()
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception(
                "[PCM:claim] DB error stealing claim claim_id=%s step=%s entry=%s "
                "from previous_owner=%s",
                claim.id,
                claim.step_name,
                claim.entry_id,
                previous_owner,
                extra={"claim_ctx": ctx},
            )
            raise

        logger.info(
            "[PCM:claim] Stole claim claim_id=%s step=%s entry=%s "
            "previous_owner=%s new_owner=%s:%s new_expiry=%s",
            claim.id,
            claim.step_name,
            claim.entry_id,
            previous_owner,
            new_owner_kind,
            new_owner_id,
            claim.lease_expires_at.isoformat(),
            extra={"claim_ctx": _claim_ctx(claim)},
        )
        logger.info(
            "[PCM:pipeline] Lease stolen for step=%s entry=%s claim_id=%s",
            claim.step_name,
            claim.entry_id,
            claim.id,
            extra={"claim_ctx": _claim_ctx(claim)},
        )

        if _is_llm_step(claim.step_name):
            logger.warning(
                "[PCM:llm] LLM step lease was stolen step=%s entry=%s claim_id=%s "
                "— previous LLM work by %s may be lost",
                claim.step_name,
                claim.entry_id,
                claim.id,
                previous_owner,
                extra={"claim_ctx": _claim_ctx(claim)},
            )
        if _is_rag_step(claim.step_name):
            logger.warning(
                "[PCM:rag] RAG step lease was stolen step=%s entry=%s claim_id=%s "
                "— previous RAG retrieval by %s may be lost",
                claim.step_name,
                claim.entry_id,
                claim.id,
                previous_owner,
                extra={"claim_ctx": _claim_ctx(claim)},
            )

        return claim

    def renew_lease(self, claim_id: str, lease_token: str) -> ProcessingJobClaim:
        """
        Renew claim lease (heartbeat).

        Raises:
            ValueError: Invalid claim_id or lease_token mismatch (claim may have been stolen).
        """
        claim = (
            self.db.query(ProcessingJobClaim)
            .filter(ProcessingJobClaim.id == claim_id)
            .first()
        )

        if not claim:
            logger.warning(
                "[PCM:claim] Lease renewal failed — claim not found claim_id=%s",
                claim_id,
            )
            raise ValueError(f"Claim not found: {claim_id}")

        if claim.lease_token != lease_token:
            logger.warning(
                "[PCM:claim] Lease token mismatch on renew claim_id=%s step=%s entry=%s "
                "— claim may have been stolen",
                claim_id,
                claim.step_name,
                claim.entry_id,
                extra={"claim_ctx": _claim_ctx(claim)},
            )
            if _is_llm_step(claim.step_name):
                logger.warning(
                    "[PCM:llm] LLM step heartbeat rejected due to stolen lease "
                    "claim_id=%s step=%s — in-flight LLM work may be orphaned",
                    claim_id,
                    claim.step_name,
                    extra={"claim_ctx": _claim_ctx(claim)},
                )
            if _is_rag_step(claim.step_name):
                logger.warning(
                    "[PCM:rag] RAG step heartbeat rejected due to stolen lease "
                    "claim_id=%s step=%s — in-flight RAG retrieval may be orphaned",
                    claim_id,
                    claim.step_name,
                    extra={"claim_ctx": _claim_ctx(claim)},
                )
            raise ValueError("Lease token mismatch (claim may have been stolen)")

        now = datetime.now(timezone.utc)
        claim.heartbeat_at = now
        claim.lease_expires_at = now + self.lease_duration
        claim.updated_at = now

        try:
            self.db.flush()
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception(
                "[PCM:claim] DB error renewing lease claim_id=%s step=%s entry=%s",
                claim_id,
                claim.step_name,
                claim.entry_id,
                extra={"claim_ctx": _claim_ctx(claim)},
            )
            raise

        logger.debug(
            "[PCM:claim] Lease renewed claim_id=%s step=%s new_expiry=%s",
            claim.id,
            claim.step_name,
            claim.lease_expires_at.isoformat(),
            extra={"claim_ctx": _claim_ctx(claim)},
        )

        return claim

    def release_claim(self, claim_id: str, lease_token: str) -> None:
        """
        Release claim explicitly.

        No-ops silently if claim not found or token mismatches (stolen claim).
        """
        claim = (
            self.db.query(ProcessingJobClaim)
            .filter(ProcessingJobClaim.id == claim_id)
            .first()
        )

        if not claim:
            logger.debug(
                "[PCM:claim] Release no-op — claim not found claim_id=%s "
                "(already released or never existed)",
                claim_id,
            )
            return

        if claim.lease_token != lease_token:
            logger.warning(
                "[PCM:claim] Release skipped — token mismatch claim_id=%s step=%s entry=%s "
                "— claim was stolen, not releasing",
                claim_id,
                claim.step_name,
                claim.entry_id,
                extra={"claim_ctx": _claim_ctx(claim)},
            )
            return

        ctx = _claim_ctx(claim)
        step_name = claim.step_name
        entry_id = claim.entry_id

        try:
            self.db.delete(claim)
            self.db.flush()
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception(
                "[PCM:claim] DB error releasing claim claim_id=%s step=%s entry=%s",
                claim_id,
                step_name,
                entry_id,
                extra={"claim_ctx": ctx},
            )
            raise

        logger.info(
            "[PCM:claim] Released claim claim_id=%s step=%s entry=%s",
            claim_id,
            step_name,
            entry_id,
            extra={"claim_ctx": ctx},
        )
        logger.info(
            "[PCM:pipeline] Claim released for step=%s entry=%s claim_id=%s",
            step_name,
            entry_id,
            claim_id,
            extra={"claim_ctx": ctx},
        )

        if _is_llm_step(step_name):
            logger.info(
                "[PCM:llm] LLM step claim released step=%s entry=%s claim_id=%s",
                step_name,
                entry_id,
                claim_id,
                extra={"claim_ctx": ctx},
            )
        if _is_rag_step(step_name):
            logger.info(
                "[PCM:rag] RAG step claim released step=%s entry=%s claim_id=%s",
                step_name,
                entry_id,
                claim_id,
                extra={"claim_ctx": ctx},
            )

    def cleanup_expired_claims(self, older_than: timedelta | None = None) -> int:
        """
        Delete claims whose lease expired more than `older_than` ago.

        Args:
            older_than: Grace period past expiry before deletion (default: 1 hour).

        Returns:
            Number of deleted claims.
        """
        if older_than is None:
            older_than = timedelta(hours=1)

        cutoff = datetime.now(timezone.utc) - older_than

        logger.info(
            "[PCM:claim] Running expired claim cleanup cutoff=%s grace_period=%s",
            cutoff.isoformat(),
            str(older_than),
        )

        # Fetch before delete so we can log LLM/RAG step details.
        expired = (
            self.db.query(ProcessingJobClaim)
            .filter(ProcessingJobClaim.lease_expires_at < cutoff)
            .all()
        )

        llm_steps = [c for c in expired if _is_llm_step(c.step_name)]
        rag_steps = [c for c in expired if _is_rag_step(c.step_name)]

        if llm_steps:
            logger.warning(
                "[PCM:llm] Cleaning up %d expired LLM step claims: %s",
                len(llm_steps),
                [(c.step_name, c.entry_id, c.owner_id) for c in llm_steps],
            )
        if rag_steps:
            logger.warning(
                "[PCM:rag] Cleaning up %d expired RAG step claims: %s",
                len(rag_steps),
                [(c.step_name, c.entry_id, c.owner_id) for c in rag_steps],
            )

        try:
            deleted_count = (
                self.db.query(ProcessingJobClaim)
                .filter(ProcessingJobClaim.lease_expires_at < cutoff)
                .delete()
            )
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception(
                "[PCM:claim] DB error during expired claim cleanup cutoff=%s",
                cutoff.isoformat(),
            )
            raise

        logger.info(
            "[PCM:claim] Expired claim cleanup complete deleted=%d cutoff=%s",
            deleted_count,
            cutoff.isoformat(),
        )

        return deleted_count
