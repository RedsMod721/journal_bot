"""
Transaction orchestrator for the entry pipeline.

Implements Section 13.5 (Transaction Model) from COMPLETE_ARCHITECTURE.md.

Transaction boundaries
----------------------
Tx A — Ingest + Initialise (short, < 100 ms)
    Creates journal_entries, processing_jobs, and processing_job_claims rows
    so the entry is durably registered before any AI work begins.
    No network calls, no AI calls.  Commits immediately.

Long-running processing (outside any transaction)
    All AI/LLM calls, RAG retrievals, and subsystem evaluations happen here.
    Results are accumulated in a PipelineContext object.

Tx B — Finalise All Writes (single atomic commit, < 500 ms)
    Writes all accumulated results (XP, quests, insights, personality, etc.)
    and marks the job as succeeded.  Enforces finalize-once via the partial
    unique index on processing_jobs.

Logging conventions
-------------------
[tx:a]          — Tx A lifecycle events
[tx:b]          — Tx B lifecycle events
[tx:pipeline]   — pipeline-level step transitions
[tx:llm]        — LLM-related write operations (personality, insight prompts)
[tx:rag]        — RAG-related write operations
[tx:error]      — error / failure paths
"""
from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from src.db.models.journal_entry import JournalEntry
from src.db.models.processing import ProcessingJob
from src.db.models.processing_distributed import ProcessingJobClaim

if TYPE_CHECKING:
    from src.ai.pipeline.pipeline_context import PipelineContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TxAError(Exception):
    """Raised when Tx A cannot complete (DB error, idempotency conflict, etc.)."""


class TxBError(Exception):
    """Raised when Tx B cannot complete atomically."""


class AlreadyFinalisedError(TxBError):
    """Raised when a succeeded record already exists for this logical job."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TX_A_LEASE_MINUTES = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log_ctx(
    *,
    user_id: str,
    entry_id: str,
    processing_run_id: str,
    job_id: Optional[str] = None,
    step: Optional[str] = None,
    tx: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "tx_ctx": {
            "user_id": user_id,
            "entry_id": entry_id,
            "processing_run_id": processing_run_id,
            "job_id": job_id,
            "step": step,
            "tx": tx,
        }
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class TransactionOrchestrator:
    """
    Orchestrate Tx A and Tx B boundaries for the entry pipeline.

    Each instance is bound to a single SQLAlchemy ``Session``.  The caller
    is responsible for managing the session lifecycle (open / close).

    Usage::

        orchestrator = TransactionOrchestrator(db)
        ids = orchestrator.execute_tx_a(user_id, content, idempotency_key)
        ctx = create_pipeline_context(...)   # outside this class
        # ... run AI steps, populate ctx ...
        orchestrator.execute_tx_b(ids["entry_id"], ids["job_id"], ctx)
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Tx A — Ingest + Initialise
    # ------------------------------------------------------------------

    def execute_tx_a(
        self,
        user_id: str,
        content: str,
        idempotency_key: str,
        step_name: str = "entry_pipeline",
    ) -> Dict[str, str]:
        """
        Execute Tx A: durably register entry + job + claim.

        This is a **short transaction** — no AI calls, no network calls.
        Commits immediately after inserting the three rows.

        Args:
            user_id:         Owner of the new entry.
            content:         Raw journal entry text.
            idempotency_key: Caller-supplied replay key (stored on claim).
            step_name:       Processing step name (default ``entry_pipeline``).

        Returns:
            ``{entry_id, job_id, processing_run_id, claim_id}``

        Raises:
            TxAError: On DB error or unexpected constraint violation.
        """
        now = _now()
        entry_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        processing_run_id = str(uuid.uuid4())
        claim_id = str(uuid.uuid4())
        lease_token = secrets.token_hex(16)

        ctx = _log_ctx(
            user_id=user_id,
            entry_id=entry_id,
            processing_run_id=processing_run_id,
            job_id=job_id,
            step=step_name,
            tx="A",
        )

        logger.info(
            "[tx:a] Starting Tx A entry=%s run=%s step=%s",
            entry_id,
            processing_run_id,
            step_name,
            extra=ctx,
        )

        # -- journal_entries ------------------------------------------------
        entry = JournalEntry(
            id=entry_id,
            user_id=user_id,
            content=content,
            status="processing",
            entry_type="text",
            created_at=now,
            updated_at=now,
        )

        # -- processing_jobs ------------------------------------------------
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            entry_id=entry_id,
            step_name=step_name,
            processing_run_id=processing_run_id,
            status="in_progress",
            attempt_count=1,
            created_at=now,
            updated_at=now,
        )

        # -- processing_job_claims ------------------------------------------
        # owner_kind must be one of: 'server_worker', 'scheduler', 'admin_recovery'
        claim = ProcessingJobClaim(
            id=claim_id,
            user_id=user_id,
            entry_id=entry_id,
            step_name=step_name,
            owner_kind="server_worker",
            owner_id="pipeline_orchestrator",
            lease_token=lease_token,
            claimed_at=now,
            lease_expires_at=now + timedelta(minutes=_TX_A_LEASE_MINUTES),
            heartbeat_at=now,
            created_at=now,
            updated_at=now,
        )

        try:
            self.db.add(entry)
            self.db.add(job)
            self.db.add(claim)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            logger.error(
                "[tx:a][tx:error] Tx A IntegrityError entry=%s run=%s — "
                "possible duplicate idempotency_key=%s: %s",
                entry_id,
                processing_run_id,
                idempotency_key,
                exc,
                extra=ctx,
            )
            raise TxAError(
                f"Tx A integrity error for idempotency_key={idempotency_key!r}"
            ) from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.error(
                "[tx:a][tx:error] Tx A DB error entry=%s run=%s: %s",
                entry_id,
                processing_run_id,
                exc,
                extra=ctx,
            )
            raise TxAError("Tx A DB error") from exc

        logger.info(
            "[tx:a] Tx A committed — entry=%s job=%s claim=%s run=%s step=%s",
            entry_id,
            job_id,
            claim_id,
            processing_run_id,
            step_name,
            extra=ctx,
        )
        logger.info(
            "[tx:pipeline] Pipeline registered step=%s entry=%s run=%s",
            step_name,
            entry_id,
            processing_run_id,
            extra=ctx,
        )

        return {
            "entry_id": entry_id,
            "job_id": job_id,
            "processing_run_id": processing_run_id,
            "claim_id": claim_id,
            "lease_token": lease_token,
        }

    # ------------------------------------------------------------------
    # Tx B — Finalise All Writes
    # ------------------------------------------------------------------

    def execute_tx_b(
        self,
        entry_id: str,
        job_id: str,
        pipeline_context: "PipelineContext",
    ) -> None:
        """
        Execute Tx B: atomically write all pipeline results.

        Persists every accumulated step output, marks the entry completed,
        and finalises the processing job.  The partial unique index
        ``uq_processing_jobs_one_success`` enforces finalize-once semantics:
        a second commit with ``status='succeeded'`` on the same logical job
        raises ``AlreadyFinalisedError``.

        **No AI calls or network calls are permitted inside this method.**

        Args:
            entry_id:         Entry that was processed.
            job_id:           Processing job to finalise.
            pipeline_context: Fully-populated context from the processing phase.

        Raises:
            AlreadyFinalisedError: Job already has a succeeded record.
            TxBError:             Any other DB failure.
        """
        ctx = _log_ctx(
            user_id=pipeline_context.user_id,
            entry_id=entry_id,
            processing_run_id=pipeline_context.processing_run_id,
            job_id=job_id,
            tx="B",
        )

        logger.info(
            "[tx:b] Starting Tx B entry=%s job=%s run=%s",
            entry_id,
            job_id,
            pipeline_context.processing_run_id,
            extra=ctx,
        )

        now = _now()

        try:
            # -- journal_entries: mark completed ----------------------------
            entry = (
                self.db.query(JournalEntry)
                .filter(
                    JournalEntry.id == entry_id,
                    JournalEntry.user_id == pipeline_context.user_id,
                )
                .first()
            )
            if entry is None:
                raise TxBError(
                    f"JournalEntry not found: entry_id={entry_id!r} "
                    f"user_id={pipeline_context.user_id!r}"
                )

            entry.status = "completed"
            entry.processed_at = now
            entry.updated_at = now

            logger.debug(
                "[tx:b] Updated journal_entries status=completed entry=%s",
                entry_id,
                extra=ctx,
            )

            # -- Step results: write each subsystem's output ---------------

            if pipeline_context.quest_result is not None:
                logger.info(
                    "[tx:b][tx:pipeline] Writing quest results entry=%s run=%s",
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                self._write_quest_results(pipeline_context, now)

            if pipeline_context.xp_result is not None:
                logger.info(
                    "[tx:b][tx:pipeline] Writing XP results entry=%s run=%s",
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                self._write_xp_results(pipeline_context, now)

            if pipeline_context.arc_result is not None:
                logger.info(
                    "[tx:b][tx:pipeline] Writing arc results entry=%s run=%s",
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                self._write_arc_results(pipeline_context, now)

            if pipeline_context.harmony_result is not None:
                logger.info(
                    "[tx:b][tx:pipeline] Writing harmony results entry=%s run=%s",
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                self._write_harmony_results(pipeline_context, now)

            if pipeline_context.forgiveness_result is not None:
                logger.info(
                    "[tx:b][tx:pipeline] Writing forgiveness results entry=%s run=%s",
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                self._write_forgiveness_results(pipeline_context, now)

            if pipeline_context.insight_result is not None:
                logger.info(
                    "[tx:b][tx:pipeline][tx:rag] Writing insight results entry=%s run=%s "
                    "(RAG-sourced insights)",
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                self._write_insight_results(pipeline_context, now)

            if pipeline_context.anomaly_result is not None:
                logger.info(
                    "[tx:b][tx:pipeline] Writing anomaly results entry=%s run=%s",
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                self._write_anomaly_results(pipeline_context, now)

            if pipeline_context.strategy_result is not None:
                logger.info(
                    "[tx:b][tx:pipeline] Writing strategy results entry=%s run=%s",
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                self._write_strategy_results(pipeline_context, now)

            if pipeline_context.personality_result is not None:
                logger.info(
                    "[tx:b][tx:pipeline][tx:llm][tx:rag] Writing personality message "
                    "entry=%s run=%s (LLM+RAG generated)",
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                self._write_personality_message(pipeline_context, now)

            if pipeline_context.report_result is not None:
                logger.info(
                    "[tx:b][tx:pipeline] Writing system report entry=%s run=%s",
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                self._write_system_report(pipeline_context, now)

            # -- Outbox events ---------------------------------------------
            if pipeline_context.outbox_events:
                logger.info(
                    "[tx:b] Writing %d outbox events entry=%s run=%s",
                    len(pipeline_context.outbox_events),
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                self._write_outbox_events(pipeline_context, now)

            # -- processing_jobs: finalise (finalize-once enforced by DB) --
            job = (
                self.db.query(ProcessingJob)
                .filter(ProcessingJob.id == job_id)
                .first()
            )
            if job is None:
                raise TxBError(f"ProcessingJob not found: job_id={job_id!r}")

            job.status = "succeeded"
            job.finalized_at = now
            job.updated_at = now
            job.ai_version_snapshot = json.dumps(
                pipeline_context.versions.as_json_dict()
            )

            # Persist non-fatal errors as final_error_message (informational).
            if pipeline_context.errors:
                non_fatal = [e for e in pipeline_context.errors if not e.get("fatal")]
                if non_fatal:
                    job.final_error_message = json.dumps(non_fatal)

            logger.debug(
                "[tx:b] Updated processing_jobs status=succeeded job=%s",
                job_id,
                extra=ctx,
            )

            # -- Atomic commit ----------------------------------------------
            self.db.commit()

        except IntegrityError as exc:
            self.db.rollback()
            # The partial unique index uq_processing_jobs_one_success triggers
            # when a second succeeded row is inserted for the same logical job.
            if "uq_processing_jobs_one_success" in str(exc):
                logger.warning(
                    "[tx:b][tx:error] Tx B finalize-once conflict — job already "
                    "succeeded job=%s entry=%s run=%s",
                    job_id,
                    entry_id,
                    pipeline_context.processing_run_id,
                    extra=ctx,
                )
                raise AlreadyFinalisedError(
                    f"Job {job_id!r} already has a succeeded record"
                ) from exc
            logger.error(
                "[tx:b][tx:error] Tx B IntegrityError job=%s entry=%s run=%s: %s",
                job_id,
                entry_id,
                pipeline_context.processing_run_id,
                exc,
                extra=ctx,
            )
            raise TxBError("Tx B integrity error") from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.error(
                "[tx:b][tx:error] Tx B DB error job=%s entry=%s run=%s: %s",
                job_id,
                entry_id,
                pipeline_context.processing_run_id,
                exc,
                extra=ctx,
            )
            raise TxBError("Tx B DB error") from exc

        logger.info(
            "[tx:b] Tx B committed — entry=%s job=%s run=%s",
            entry_id,
            job_id,
            pipeline_context.processing_run_id,
            extra=ctx,
        )
        logger.info(
            "[tx:pipeline] Pipeline finalised entry=%s run=%s errors=%d",
            entry_id,
            pipeline_context.processing_run_id,
            len(pipeline_context.errors),
            extra=ctx,
        )

    # ------------------------------------------------------------------
    # Tx B write helpers
    # ------------------------------------------------------------------
    # These methods run INSIDE the Tx B session — no commits, no network
    # calls.  Each receives the full PipelineContext so it can access
    # identity fields and version snapshots.
    # ------------------------------------------------------------------

    def _write_quest_results(
        self, ctx: "PipelineContext", now: datetime
    ) -> None:
        """
        Persist quest matches (instant/streak) and progress updates.

        Delegates to the quest service once that subsystem is implemented.
        Currently a no-op placeholder that logs the intent.
        """
        result = ctx.quest_result
        logger.debug(
            "[tx:b][tx:pipeline] _write_quest_results entry=%s "
            "instant_quests=%d streak_quests=%d",
            ctx.entry_id,
            len(result.get("instant_quests", [])),
            len(result.get("streak_quests", [])),
        )
        # TODO(mb-next): call QuestService.apply_quest_results(db, ctx)

    def _write_xp_results(
        self, ctx: "PipelineContext", now: datetime
    ) -> None:
        """
        Insert XpAward rows and update skill/theme XP totals.

        Delegates to the XP service.  Award identity keys are pre-computed
        by the XP calculator step to satisfy Section 10 idempotency.
        """
        result = ctx.xp_result
        logger.debug(
            "[tx:b][tx:pipeline] _write_xp_results entry=%s awards=%d",
            ctx.entry_id,
            len(result.get("awards", [])),
        )
        # TODO(mb-next): call XpService.apply_xp_awards(db, ctx)

    def _write_arc_results(
        self, ctx: "PipelineContext", now: datetime
    ) -> None:
        """Update story arc state and multiplier from arc evaluation output."""
        logger.debug(
            "[tx:b][tx:pipeline] _write_arc_results entry=%s arc_id=%s",
            ctx.entry_id,
            ctx.arc_result.get("arc_id") if ctx.arc_result else None,
        )
        # TODO(mb-next): call StoryArcService.apply_arc_results(db, ctx)

    def _write_harmony_results(
        self, ctx: "PipelineContext", now: datetime
    ) -> None:
        """Persist harmony dimension snapshot for this entry."""
        logger.debug(
            "[tx:b][tx:pipeline] _write_harmony_results entry=%s",
            ctx.entry_id,
        )
        # TODO(mb-next): call HarmonyService.apply_harmony_results(db, ctx)

    def _write_forgiveness_results(
        self, ctx: "PipelineContext", now: datetime
    ) -> None:
        """Update forgiveness/decay snapshot based on pipeline evaluation."""
        logger.debug(
            "[tx:b][tx:pipeline] _write_forgiveness_results entry=%s",
            ctx.entry_id,
        )
        # TODO(mb-next): call ForgivenessService.apply_forgiveness_results(db, ctx)

    def _write_insight_results(
        self, ctx: "PipelineContext", now: datetime
    ) -> None:
        """
        Insert insight rows and evidence links.

        Insights are LLM-generated and RAG-augmented (logged at [tx:rag]).
        """
        result = ctx.insight_result
        logger.debug(
            "[tx:b][tx:pipeline][tx:rag] _write_insight_results entry=%s "
            "insights=%d rag_hits=%d",
            ctx.entry_id,
            len(result.get("insights", [])),
            len(result.get("rag_hits", [])),
        )
        # TODO(mb-next): call InsightService.apply_insight_results(db, ctx)

    def _write_anomaly_results(
        self, ctx: "PipelineContext", now: datetime
    ) -> None:
        """Persist anomaly score record for this entry."""
        logger.debug(
            "[tx:b][tx:pipeline] _write_anomaly_results entry=%s score=%s",
            ctx.entry_id,
            ctx.anomaly_result.get("anomaly_score") if ctx.anomaly_result else None,
        )
        # TODO(mb-next): call AnomalyService.apply_anomaly_results(db, ctx)

    def _write_strategy_results(
        self, ctx: "PipelineContext", now: datetime
    ) -> None:
        """Update strategy tracking state from pipeline evaluation."""
        logger.debug(
            "[tx:b][tx:pipeline] _write_strategy_results entry=%s",
            ctx.entry_id,
        )
        # TODO(mb-next): call StrategyService.apply_strategy_results(db, ctx)

    def _write_personality_message(
        self, ctx: "PipelineContext", now: datetime
    ) -> None:
        """
        Insert personality_messages row.

        This step is driven by an LLM call (logged at [tx:llm]) with RAG
        context (logged at [tx:rag]) captured during the processing phase.
        The write itself is purely a DB insert — no LLM calls here.
        """
        result = ctx.personality_result
        logger.debug(
            "[tx:b][tx:pipeline][tx:llm][tx:rag] _write_personality_message "
            "entry=%s model=%s:%s prompt_version=%s",
            ctx.entry_id,
            ctx.versions.ai_model_id,
            ctx.versions.ai_model_version,
            ctx.versions.personality_message_prompt_version,
        )
        # TODO(mb-next): call PersonalityService.apply_personality_message(db, ctx)

    def _write_system_report(
        self, ctx: "PipelineContext", now: datetime
    ) -> None:
        """
        Insert system report as a PersonalityMessage(personality='system') row.

        The report is deterministic (no LLM) and was assembled in step 15b.
        The unique constraint uq_personality_messages_selector_slot on
        (user_id, entry_id, message_type, logical_slot_key, selector_version)
        makes pipeline retries idempotent.
        """
        from src.db.models.personality import PersonalityMessage

        result = ctx.report_result
        if not result:
            logger.debug(
                "[tx:b][tx:pipeline] _write_system_report skipped — no report_result entry=%s",
                ctx.entry_id,
            )
            return

        row = PersonalityMessage(
            id=str(uuid.uuid4()),
            user_id=ctx.user_id,
            entry_id=ctx.entry_id,
            personality="system",
            message_type="report_summary",
            message_text=result.get("message_text", "[SYSTEM] No report available."),
            selector_version=result.get("selector_version", 1),
            selector_seed_hash=None,
            logical_slot_key=result.get("logical_slot_key", "system_report"),
            context_data=json.dumps(result.get("context_data", {})),
            quest_id=None,
            created_at=now,
        )
        self.db.add(row)
        logger.debug(
            "[tx:b][tx:pipeline] _write_system_report entry=%s fallback=%s",
            ctx.entry_id,
            result.get("fallback_used", False),
        )

    def _write_outbox_events(
        self, ctx: "PipelineContext", now: datetime
    ) -> None:
        """
        Insert pending outbox_events rows for downstream dispatch.

        Events were enqueued during processing via
        ``PipelineContext.queue_outbox_event()``.
        """
        from src.db.models.processing import OutboxEvent  # local import

        for evt in ctx.outbox_events:
            dedupe_key = (
                f"{ctx.processing_run_id}:{evt['event_type']}"
                f":{uuid.uuid4().hex[:8]}"
            )
            row = OutboxEvent(
                id=str(uuid.uuid4()),
                user_id=ctx.user_id,
                entry_id=ctx.entry_id,
                processing_run_id=ctx.processing_run_id,
                event_type=evt["event_type"],
                event_dedupe_key=dedupe_key,
                payload_json=json.dumps(evt["payload"]),
                status="pending",
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            logger.debug(
                "[tx:b] Queued outbox event type=%s dedupe_key=%s entry=%s",
                evt["event_type"],
                dedupe_key,
                ctx.entry_id,
            )

    # ------------------------------------------------------------------
    # Failure path
    # ------------------------------------------------------------------

    def mark_job_failed(
        self,
        job_id: str,
        error_code: str,
        error_message: str,
        *,
        entry_id: Optional[str] = None,
        processing_run_id: Optional[str] = None,
    ) -> None:
        """
        Mark a processing job as failed (called from the outer error handler).

        Sets ``processing_jobs.status = 'failed'`` and records the error code
        and message.  Also reverts the journal entry status back to ``'failed'``
        if ``entry_id`` is provided.

        This runs in its own short transaction so it succeeds even when the
        main processing session has been rolled back.
        """
        ctx = _log_ctx(
            user_id="unknown",
            entry_id=entry_id or "unknown",
            processing_run_id=processing_run_id or "unknown",
            job_id=job_id,
            tx="failure",
        )
        logger.error(
            "[tx:error] Marking job failed job=%s entry=%s error_code=%s: %s",
            job_id,
            entry_id,
            error_code,
            error_message,
            extra=ctx,
        )

        now = _now()
        try:
            job = (
                self.db.query(ProcessingJob)
                .filter(ProcessingJob.id == job_id)
                .first()
            )
            if job is not None:
                job.status = "failed"
                job.final_error_code = error_code[:100]
                job.final_error_message = error_message
                job.finalized_at = now
                job.updated_at = now

            if entry_id is not None:
                entry = (
                    self.db.query(JournalEntry)
                    .filter(JournalEntry.id == entry_id)
                    .first()
                )
                if entry is not None:
                    entry.status = "failed"
                    entry.error_message = error_message
                    entry.updated_at = now

            self.db.commit()
            logger.info(
                "[tx:error] Job failure persisted job=%s entry=%s error_code=%s",
                job_id,
                entry_id,
                error_code,
                extra=ctx,
            )
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.exception(
                "[tx:error] Failed to persist job failure record job=%s: %s",
                job_id,
                exc,
                extra=ctx,
            )
