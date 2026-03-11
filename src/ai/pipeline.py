"""17-Step AI Processing Pipeline for RPG Life Tracker.

Architecture
------------
The pipeline is split across two layers:

``src/ai/steps/``
    Pure-function step modules.  Each module is independently importable,
    testable, and replaceable without touching the orchestrator.  All
    dependencies (db session, clients, version constants) are passed as
    keyword arguments.

``PipelineProcessor``  (this module)
    Synchronous orchestrator.  Owns idempotency enforcement, processing-job
    audit trail, transactional outbox events, and per-step timing/status
    recording.  Delegates all business logic to the step modules.

``JournalEntryPipeline``  (this module)
    Async public facade intended for FastAPI route handlers and background
    workers.  Wraps ``PipelineProcessor`` so the event loop stays unblocked,
    and auto-derives idempotency keys when callers do not supply one.

Version pins
------------
``PIPELINE_VERSION``  — bump when orchestration logic changes.
``RULESET_VERSION``   — bump when XP/reward calculation rules change.
Both are embedded in every XpAward row for audit and replay purposes.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from src.ai.cache import StepCache
from src.ai.ollama import OllamaClient
from src.ai.qdrant import QdrantClientAdapter
from src.ai.recovery import RecoveryQueue

# Step modules — each encapsulates the business logic for one or more steps.
from src.ai.steps import anomaly as _s_anomaly
from src.ai.steps import embedding as _s_embedding
from src.ai.steps import entry as _s_entry
from src.ai.steps import insights as _s_insights
from src.ai.steps import normalize as _s_normalize
from src.ai.steps import progression as _s_progression
from src.ai.steps import quests as _s_quests
from src.ai.steps import rag as _s_rag
from src.ai.steps import rewards as _s_rewards
from src.ai.steps import signals as _s_signals
from src.ai.steps import strategy as _s_strategy
from src.ai.steps import structured as _s_structured
from src.ai.steps import summary as _s_summary
from src.ai.steps import variety as _s_variety

from src.core.forgiveness_decay_service import ForgivenessDecayService
from src.core.harmony_classifier import HarmonyClassifier
from src.core.harmony_refresh_service import HarmonyRefreshService
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.processing import (
    EntryIdempotencyClaim,
    OutboxEvent,
    ProcessingJob,
    ProcessingJobAttempt,
)

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "week3-v2"
RULESET_VERSION = "s10-v8"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PipelineStepError(RuntimeError):
    """Raised when a mandatory pipeline step fails irrecoverably."""

    def __init__(self, step_name: str, error_code: str, message: str) -> None:
        super().__init__(message)
        self.step_name = step_name
        self.error_code = error_code


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso8601z(ts: datetime) -> str:
    return (
        ts.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _derive_idempotency_key(user_id: str, entry_id: str) -> str:
    """Derive a deterministic idempotency key from (user_id, entry_id, PIPELINE_VERSION).

    The key is a 32-hex-character prefix of a SHA-256 digest, long enough to
    be collision-resistant in practice while remaining compact in the DB.
    """
    raw = f"{user_id}:{entry_id}:{PIPELINE_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Private step helpers — called from within _run_steps lambdas
# ---------------------------------------------------------------------------


def _harmony_step(
    *,
    user_id: str,
    entry_id: str,
    entry: Any,
    db: Session,
) -> dict[str, Any]:
    """Classify harmony dimensions from structured data and refresh scores."""
    structured_orm: JournalEntryStructured | None = (
        db.query(JournalEntryStructured)
        .filter(
            JournalEntryStructured.user_id == user_id,
            JournalEntryStructured.entry_id == entry_id,
        )
        .one_or_none()
    )

    dims: set[str] = set()
    if structured_orm is not None:
        dims = HarmonyClassifier(db).classify_dimensions(entry, structured_orm)

    result = HarmonyRefreshService(db).refresh_harmony(
        user_id=user_id,
        now_utc=_now_utc(),
        advance_overwork_state=True,
    )
    db.flush()

    return {
        "dimensions_addressed": sorted(dims),
        "overall_balance": float(result.harmony.overall_balance or 0.5),
        "overwork_stage": int(result.harmony.overwork_stage or 0),
    }


def _staleness_reset_step(
    *,
    user_id: str,
    skill_awards: list[dict[str, Any]],
    now_utc: datetime,
    db: Session,
) -> dict[str, Any]:
    """Reinforce skill staleness for every skill that received XP this run."""
    from src.db.models.skill import Skill

    skill_xp: dict[str, int] = {}
    for award in skill_awards:
        if award.get("replayed"):
            continue
        sid = award.get("skill_id")
        if sid:
            skill_xp[sid] = skill_xp.get(sid, 0) + int(award.get("amount", 0))

    if not skill_xp:
        return {"skills_reset": 0}

    skills = (
        db.query(Skill)
        .filter(Skill.user_id == user_id, Skill.id.in_(list(skill_xp.keys())))
        .all()
    )
    decay_svc = ForgivenessDecayService(db)
    for skill in skills:
        decay_svc.reinforce_skill(
            skill,
            now_utc,
            is_primary=True,
            xp_amount=skill_xp.get(skill.id, 0),
        )

    db.flush()
    return {"skills_reset": len(skills)}


# ---------------------------------------------------------------------------
# PipelineProcessor — synchronous orchestrator
# ---------------------------------------------------------------------------


class PipelineProcessor:
    """Synchronous orchestrator for the 17-step journal entry pipeline.

    Responsibilities
    ----------------
    - Idempotency: claims a ``EntryIdempotencyClaim`` before starting; replays
      the stored result on duplicate calls with the same idempotency key.
    - Job audit trail: creates ``ProcessingJob`` + ``ProcessingJobAttempt``
      records so every run (including failures) is observable.
    - Per-step telemetry: wraps each step in ``run_step`` which records status,
      duration, input/output snapshots, and error codes.
    - Transactional outbox: emits ``entry.processed`` / ``entry.processing_failed``
      events via a dedup-keyed ``OutboxEvent`` table.
    - Graceful degradation: non-critical steps (embedding, RAG) are marked
      ``allow_degraded=True``; the pipeline completes with reduced capability
      rather than failing entirely.

    Step business logic is fully delegated to ``src.ai.steps.*`` modules.
    """

    def __init__(
        self,
        db: Session,
        ollama: OllamaClient | None = None,
        qdrant: QdrantClientAdapter | None = None,
        cache: StepCache | None = None,
        recovery: RecoveryQueue | None = None,
    ) -> None:
        self.db = db
        self.ollama = ollama or OllamaClient()
        self.qdrant = qdrant or self._build_default_qdrant()
        self.cache = cache or StepCache(ttl_hours=24)
        self.recovery = recovery

    @staticmethod
    def _build_default_qdrant() -> Any:
        try:
            return QdrantClientAdapter()
        except Exception:

            class _NoQdrant:
                def ensure_collection(self) -> None:
                    return None

                def search(
                    self, _vector: list[float], limit: int = 5
                ) -> list[dict[str, Any]]:
                    return []

            return _NoQdrant()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def process_entry(
        self, entry_id: str, user_id: str, idempotency_key: str
    ) -> dict[str, Any]:
        """Process a journal entry through the full 17-step pipeline.

        Args:
            entry_id:         Journal entry UUID.
            user_id:          Owning user UUID.
            idempotency_key:  Caller-supplied dedup key.  Use
                              ``_derive_idempotency_key`` for auto-derivation.

        Returns:
            Processing result dict with ``status``, ``summary``, ``steps``,
            and ``meta`` keys.  When replayed, also contains ``replayed: True``.

        Raises:
            PipelineStepError: When a mandatory step fails.
        """
        replay = self._get_idempotent_replay(user_id, idempotency_key)
        if replay is not None:
            return replay

        processing_run_id = str(uuid.uuid4())

        entry = self._get_entry(user_id=user_id, entry_id=entry_id)
        if entry is None:
            raise PipelineStepError(
                "validate_input",
                "ENTRY_NOT_FOUND",
                f"journal entry {entry_id} for user {user_id} not found",
            )

        self._claim_idempotency(user_id, entry_id, idempotency_key, processing_run_id)
        job = self._upsert_job(user_id, entry_id, processing_run_id)
        self._create_attempt(job.id, 1, status="started")

        entry.status = "processing"
        entry.error_message = None
        self.db.commit()

        try:
            result = self._run_steps(
                entry_id=entry_id,
                user_id=user_id,
                processing_run_id=processing_run_id,
            )
            job.status = "completed"
            job.result_json = json.dumps(result, sort_keys=True)
            self._create_attempt(job.id, 2, status="completed")
            self._mark_claim_completed(user_id, idempotency_key)
            self._emit_outbox_event(
                user_id=user_id,
                event_type="entry.processed",
                payload=result,
            )
            self.db.commit()
            logger.info(
                "pipeline completed run=%s user=%s entry=%s idempotency=%s",
                processing_run_id,
                user_id,
                entry_id,
                idempotency_key,
            )
            return result
        except Exception as exc:
            self.db.rollback()
            error_code = (
                exc.error_code
                if isinstance(exc, PipelineStepError)
                else "PIPELINE_EXCEPTION"
            )
            try:
                self._record_failure(
                    job_id=job.id,
                    user_id=user_id,
                    entry_id=entry_id,
                    key=idempotency_key,
                    processing_run_id=processing_run_id,
                    error=str(exc),
                    error_code=error_code,
                )
            except Exception as record_exc:
                # DB is likely down — fall back to the file-based recovery queue
                # so no entry is silently lost.
                logger.critical(
                    "pipeline failure_recording failed run=%s entry=%s record_error=%s"
                    " — saving to recovery queue",
                    processing_run_id,
                    entry_id,
                    record_exc,
                )
                self._save_to_recovery(
                    entry_id=entry_id,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    error=str(exc),
                    error_code=error_code,
                )
            raise

    # ------------------------------------------------------------------
    # Step orchestration
    # ------------------------------------------------------------------

    def _run_steps(
        self, *, entry_id: str, user_id: str, processing_run_id: str
    ) -> dict[str, Any]:
        """Execute all 17 steps in sequence, recording per-step telemetry.

        Each step is wrapped in ``run_step`` which handles timing, status,
        and degraded-mode fallback.  Step business logic is fully delegated
        to the ``src.ai.steps.*`` modules.
        """
        run_started = _now_utc()
        steps: dict[str, Any] = {}
        degraded_codes: list[str] = []

        def run_step(
            *,
            step_name: str,
            step_input: dict[str, Any],
            fn: Callable[[], dict[str, Any]],
            error_code: str,
            allow_degraded: bool = False,
            degraded_builder: Callable[[Exception], dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            """Execute *fn*, record telemetry, and handle degraded fallback."""
            started = time.perf_counter()
            started_at = _now_utc()
            record: dict[str, Any] = {
                "status": "failed",
                "input": step_input,
                "output": {},
                "error_code": error_code,
            }
            try:
                output = fn()
                record = {
                    "status": "completed",
                    "input": step_input,
                    "output": output,
                    "error_code": None,
                }
                return output
            except Exception as exc:
                if not allow_degraded:
                    raise PipelineStepError(step_name, error_code, str(exc)) from exc
                degraded_codes.append(error_code)
                output = degraded_builder(exc) if degraded_builder else {}
                record = {
                    "status": "degraded",
                    "input": step_input,
                    "output": output,
                    "error_code": error_code,
                    "error": str(exc),
                }
                return output
            finally:
                duration_ms = int((time.perf_counter() - started) * 1000)
                record["duration_ms"] = duration_ms
                record["started_at"] = _iso8601z(started_at)
                steps[step_name] = record
                logger.info(
                    "pipeline step run=%s step=%s status=%s duration_ms=%s",
                    processing_run_id,
                    step_name,
                    record["status"],
                    duration_ms,
                )

        # ── Load entry ──────────────────────────────────────────────────
        entry = self._get_entry(user_id=user_id, entry_id=entry_id)
        if entry is None:
            raise PipelineStepError(
                "step_01_validate_input",
                "STEP_01_INVALID_INPUT",
                f"journal entry {entry_id} for user {user_id} not found",
            )

        # ── Step 01: Validate input ──────────────────────────────────────
        run_step(
            step_name="step_01_validate_input",
            step_input={"entry_id": entry_id, "user_id": user_id},
            error_code="STEP_01_INVALID_INPUT",
            fn=lambda: {
                "entry_status": entry.status,
                "entry_type": entry.entry_type,
                "entry_id": entry.id,
            },
        )

        # ── Step 02: Load entry ──────────────────────────────────────────
        run_step(
            step_name="step_02_load_entry",
            step_input={"entry_id": entry_id},
            error_code="STEP_02_LOAD_ENTRY",
            fn=lambda: {
                "entry_status": entry.status,
                "entry_type": entry.entry_type,
                "content_length": len(entry.content or ""),
            },
        )

        # ── Step 03: Normalise text ──────────────────────────────────────
        normalized = run_step(
            step_name="step_03_normalize_text",
            step_input={"content_length": len(entry.content or "")},
            error_code="STEP_03_NORMALIZE",
            fn=lambda: _s_normalize.run(entry.content or ""),
        )

        # ── Step 04: Ollama health ───────────────────────────────────────
        ollama_health = run_step(
            step_name="step_04_ollama_health",
            step_input={"model": getattr(self.ollama, "model", "unknown")},
            error_code="STEP_04_OLLAMA_HEALTH",
            allow_degraded=True,
            degraded_builder=lambda exc: {
                "connected": False,
                "model_available": False,
                "models": [],
                "error": str(exc),
            },
            fn=lambda: self.ollama.health(),
        )

        # ── Step 05: Generate embedding ──────────────────────────────────
        embedding = run_step(
            step_name="step_05_embedding",
            step_input={
                "cache_key": f"embedding:{entry_id}",
                "ollama_connected": bool(ollama_health.get("connected")),
            },
            error_code="STEP_05_EMBEDDING",
            allow_degraded=True,
            degraded_builder=lambda _exc: {
                "vector": [0.0] * 8,
                "from_cache": False,
                "fallback": True,
            },
            fn=lambda: _s_embedding.run(
                entry_id=entry_id,
                normalized_text=normalized["canonical_text"],
                ollama_health=ollama_health,
                ollama=self.ollama,
                cache=self.cache,
            ),
        )

        # ── Step 06: RAG search ──────────────────────────────────────────
        rag = run_step(
            step_name="step_06_rag_search",
            step_input={"embedding_dims": len(embedding.get("vector", []))},
            error_code="STEP_06_RAG_SEARCH",
            allow_degraded=True,
            degraded_builder=lambda exc: {
                "hits": [],
                "hit_count": 0,
                "fallback": True,
                "error": str(exc),
            },
            fn=lambda: _s_rag.run(
                vector=embedding.get("vector", []),
                qdrant=self.qdrant,
                cache=self.cache,
                entry_id=entry_id,
            ),
        )

        # ── Step 07: Detect signals ──────────────────────────────────────
        # allow_degraded=True: the Skill DB query may fail when the DB is
        # partially unavailable (e.g. the skills table is locked).  Downstream
        # steps tolerate empty skill/activity lists, so the pipeline can still
        # award quests, persist XP, and produce insights in degraded mode.
        detection = run_step(
            step_name="step_07_detect_signals",
            step_input={
                "canonical_text_length": len(normalized["canonical_text"]),
                "rag_hit_count": rag.get("hit_count", 0),
            },
            error_code="STEP_07_SIGNAL_DETECTION",
            allow_degraded=True,
            degraded_builder=lambda _exc: {
                "detected_skills": [],
                "detected_activities": [],
                "dominant_emotions": [],
                "energy_level": 5,
                "self_compassion_score": 7,
                "task_type": "analytical",
            },
            fn=lambda: _s_signals.run(
                user_id=user_id,
                canonical_text=normalized["canonical_text"],
                db=self.db,
            ),
        )

        # ── Step 08: Persist structured data ────────────────────────────
        structured = run_step(
            step_name="step_08_upsert_structured",
            step_input={
                "detected_skills": detection["detected_skills"],
                "detected_activities": detection["detected_activities"],
            },
            error_code="STEP_08_STRUCTURED_PERSIST",
            fn=lambda: _s_structured.run(
                user_id=user_id,
                entry_id=entry_id,
                canonical_text=normalized["canonical_text"],
                detection=detection,
                db=self.db,
            ),
        )

        # ── Step 08a: Variety multiplier ─────────────────────────────────
        variety_out = run_step(
            step_name="step_08a_calculate_variety",
            step_input={"user_id": user_id, "window_days": 30},
            error_code="STEP_08A_VARIETY",
            allow_degraded=True,
            degraded_builder=lambda _exc: {
                "active_skill_count_30d": 0,
                "variety_multiplier_bp": 10000,
                "window_days": 30,
            },
            fn=lambda: _s_variety.run(user_id=user_id, db=self.db),
        )

        # ── Step 08b: Anomaly precheck ────────────────────────────────────
        anomaly_precheck = run_step(
            step_name="step_08b_anomaly_precheck",
            step_input={"detected_skills": detection["detected_skills"]},
            error_code="STEP_08B_ANOMALY_PRECHECK",
            allow_degraded=True,
            degraded_builder=lambda _exc: {
                "troll_bp": 10000,
                "troll_multiplier": 1.0,
                "anomaly_score": 0.0,
                "reasons": [],
            },
            fn=lambda: _s_anomaly.precheck(
                user_id=user_id,
                detected_skills=detection["detected_skills"],
                db=self.db,
            ),
        )

        # ── Step 08c: Detect balance strategies ──────────────────────────
        strategy_out = run_step(
            step_name="step_08c_detect_strategies",
            step_input={
                "detected_skills": detection["detected_skills"],
                "anomaly_score": anomaly_precheck.get("anomaly_score", 0.0),
            },
            error_code="STEP_08C_STRATEGY_DETECT",
            allow_degraded=True,
            degraded_builder=lambda _exc: {
                "detected_strategies": [],
                "strategy_scores": {},
            },
            fn=lambda: _s_strategy.run(
                user_id=user_id,
                entry_id=entry_id,
                canonical_text=normalized["canonical_text"],
                detection=detection,
                anomaly_score=anomaly_precheck.get("anomaly_score", 0.0),
                db=self.db,
            ),
        )

        # ── Step 08d: Harmony classify & refresh ─────────────────────────
        harmony_out = run_step(
            step_name="step_08d_harmony_refresh",
            step_input={"entry_id": entry_id, "user_id": user_id},
            error_code="STEP_08D_HARMONY_REFRESH",
            allow_degraded=True,
            degraded_builder=lambda _exc: {
                "dimensions_addressed": [],
                "overall_balance": 0.5,
                "overwork_stage": 0,
            },
            fn=lambda: _harmony_step(
                user_id=user_id,
                entry_id=entry_id,
                entry=entry,
                db=self.db,
            ),
        )

        # ── Step 09: Match quests ────────────────────────────────────────
        matched = run_step(
            step_name="step_09_match_quests",
            step_input={
                "detected_skills": detection["detected_skills"],
                "detected_activities": detection["detected_activities"],
            },
            error_code="STEP_09_QUEST_MATCH",
            fn=lambda: _s_quests.match(
                entry=entry,
                user_id=user_id,
                detected_skills=detection["detected_skills"],
                detected_activities=detection["detected_activities"],
                db=self.db,
            ),
        )

        # ── Step 10: Update quest progress ──────────────────────────────
        progress = run_step(
            step_name="step_10_update_quest_progress",
            step_input={"matched_count": len(matched["matched_quest_ids"])},
            error_code="STEP_10_QUEST_PROGRESS",
            fn=lambda: _s_quests.update_progress(
                entry=entry,
                user_id=user_id,
                matched_quest_ids=matched["matched_quest_ids"],
                db=self.db,
            ),
        )

        # ── Step 11: Compute quest rewards ──────────────────────────────
        quest_rewards = run_step(
            step_name="step_11_compute_quest_rewards",
            step_input={
                "completed_quest_ids": progress["completed_quest_ids"],
                "matched_quest_count": len(matched["matched_quest_ids"]),
            },
            error_code="STEP_11_QUEST_REWARDS",
            fn=lambda: _s_rewards.compute_quest_rewards(
                completed_quests=progress["completed_quest_payloads"],
                variety_multiplier_bp=variety_out.get("variety_multiplier_bp", 10000),
                troll_bp=anomaly_precheck.get("troll_bp", 10000),
                diminishing_bp=strategy_out.get("diminishing_bp", 10000),
            ),
        )

        # ── Step 12: Persist skill awards ───────────────────────────────
        skill_awards = run_step(
            step_name="step_12_persist_skill_awards",
            step_input={"quest_rewards": quest_rewards["rewards"]},
            error_code="STEP_12_SKILL_AWARD_PERSIST",
            fn=lambda: _s_rewards.persist_skill_awards(
                user_id=user_id,
                entry_id=entry_id,
                processing_run_id=processing_run_id,
                rewards=quest_rewards["rewards"],
                db=self.db,
                pipeline_version=PIPELINE_VERSION,
                ruleset_version=RULESET_VERSION,
            ),
        )

        # ── Step 13: Persist theme awards ───────────────────────────────
        theme_awards = run_step(
            step_name="step_13_persist_theme_awards",
            step_input={"skill_award_count": len(skill_awards["skill_awards"])},
            error_code="STEP_13_THEME_AWARD_PERSIST",
            fn=lambda: _s_rewards.persist_theme_awards(
                user_id=user_id,
                entry_id=entry_id,
                processing_run_id=processing_run_id,
                skill_awards=skill_awards["skill_awards"],
                db=self.db,
                pipeline_version=PIPELINE_VERSION,
                ruleset_version=RULESET_VERSION,
            ),
        )

        # ── Step 14: Update progression counters ────────────────────────
        run_step(
            step_name="step_14_update_progression_counters",
            step_input={
                "skill_award_count": len(skill_awards["skill_awards"]),
                "theme_award_count": len(theme_awards["theme_awards"]),
            },
            error_code="STEP_14_COUNTER_UPDATES",
            fn=lambda: _s_progression.update_counters(
                skill_awards=skill_awards["skill_awards"],
                theme_awards=theme_awards["theme_awards"],
                db=self.db,
                user_id=user_id,
                entry_id=entry_id,
            ),
        )

        # ── Step 14b: Generate insight ───────────────────────────────────
        insight = run_step(
            step_name="step_14b_generate_insight",
            step_input={"entry_id": entry_id, "rag_hit_count": rag.get("hit_count", 0)},
            error_code="STEP_14B_INSIGHT",
            allow_degraded=True,
            degraded_builder=lambda _exc: {
                "insight_id": None,
                "insight_text": "",
                "insight_category": "general",
                "insight_confidence": 0.5,
                "from_ollama": False,
            },
            fn=lambda: _s_insights.run(
                user_id=user_id,
                entry_id=entry_id,
                canonical_text=normalized["canonical_text"],
                rag_hits=rag.get("hits", []),
                detection=detection,
                ollama_health=ollama_health,
                ollama=self.ollama,
                db=self.db,
                cache=self.cache,
            ),
        )

        # ── Step 14c: Record anomaly score ───────────────────────────────
        anomaly_record = run_step(
            step_name="step_14c_record_anomaly",
            step_input={"anomaly_score": anomaly_precheck.get("anomaly_score", 0.0)},
            error_code="STEP_14C_ANOMALY_RECORD",
            allow_degraded=True,
            degraded_builder=lambda _exc: {
                "anomaly_id": None,
                "anomaly_score": 0.0,
                "skill_xp_total": 0,
            },
            fn=lambda: _s_anomaly.record(
                user_id=user_id,
                entry_id=entry_id,
                anomaly_score=anomaly_precheck.get("anomaly_score", 0.0),
                reasons=anomaly_precheck.get("reasons", []),
                skill_xp_total=sum(
                    a["amount"]
                    for a in skill_awards["skill_awards"]
                    if not a.get("replayed")
                ),
                db=self.db,
            ),
        )

        # ── Step 14d: Reset skill staleness ──────────────────────────────
        run_step(
            step_name="step_14d_reset_staleness",
            step_input={"skill_award_count": len(skill_awards["skill_awards"])},
            error_code="STEP_14D_STALENESS_RESET",
            allow_degraded=True,
            degraded_builder=lambda _exc: {"skills_reset": 0},
            fn=lambda: _staleness_reset_step(
                user_id=user_id,
                skill_awards=skill_awards["skill_awards"],
                now_utc=run_started,
                db=self.db,
            ),
        )

        # ── Step 15: Build result summary ───────────────────────────────
        result_summary = run_step(
            step_name="step_15_build_summary",
            step_input={
                "structured_id": structured["structured_id"],
                "rag_hit_count": rag.get("hit_count", 0),
            },
            error_code="STEP_15_BUILD_SUMMARY",
            fn=lambda: _s_summary.build(
                rag_hits=rag.get("hits", []),
                detection=detection,
                progress=progress,
                skill_awards=skill_awards,
                theme_awards=theme_awards,
                variety=variety_out,
                anomaly=anomaly_precheck,
                insight=insight,
                detected_strategies=strategy_out.get("detected_strategies", []),
                strategy=strategy_out,
            ),
        )

        # ── Step 16: Mark entry completed ───────────────────────────────
        run_step(
            step_name="step_16_mark_entry_completed",
            step_input={"entry_id": entry_id},
            error_code="STEP_16_ENTRY_FINALIZE",
            fn=lambda: _s_entry.mark_completed(
                entry=entry,
                run_started=run_started,
                db=self.db,
            ),
        )

        # ── Step 17: Finalise payload ────────────────────────────────────
        pipeline_meta = run_step(
            step_name="step_17_finalize_payload",
            step_input={"degraded_codes": degraded_codes},
            error_code="STEP_17_FINALIZE_PAYLOAD",
            fn=lambda: {
                "pipeline_version": PIPELINE_VERSION,
                "ruleset_version": RULESET_VERSION,
                "degraded": bool(degraded_codes),
                "degraded_codes": sorted(degraded_codes),
                "anomaly_id": anomaly_record.get("anomaly_id"),
            },
        )

        # Emit cache statistics so operators can tune TTL / max_size.
        _cache_stats = self.cache.get_stats()
        logger.info(
            "pipeline cache_stats run=%s hit_rate=%.2f hits=%s misses=%s"
            " evictions=%s size=%s/%s",
            processing_run_id,
            _cache_stats["hit_rate"],
            _cache_stats["hits"],
            _cache_stats["misses"],
            _cache_stats["evictions"],
            _cache_stats["size"],
            _cache_stats["max_size"],
        )

        return {
            "entry_id": entry_id,
            "user_id": user_id,
            "processing_run_id": processing_run_id,
            "status": "completed",
            "completed_at": _iso8601z(_now_utc()),
            "steps": steps,
            "summary": result_summary,
            "meta": {**pipeline_meta, "cache_stats": _cache_stats},
        }

    # ------------------------------------------------------------------
    # Idempotency & job-tracking infrastructure
    # ------------------------------------------------------------------

    def _claim_idempotency(
        self, user_id: str, entry_id: str, key: str, processing_run_id: str
    ) -> None:
        claim = EntryIdempotencyClaim(
            user_id=user_id,
            idempotency_key=key,
            entry_id=entry_id,
            processing_run_id=processing_run_id,
            status="claimed",
        )
        self.db.add(claim)
        self.db.flush()

    def _get_idempotent_replay(self, user_id: str, key: str) -> dict[str, Any] | None:
        claim = (
            self.db.query(EntryIdempotencyClaim)
            .filter(
                EntryIdempotencyClaim.user_id == user_id,
                EntryIdempotencyClaim.idempotency_key == key,
            )
            .one_or_none()
        )
        if claim is None:
            return None

        if claim.processing_run_id:
            job = (
                self.db.query(ProcessingJob)
                .filter(
                    ProcessingJob.user_id == user_id,
                    ProcessingJob.processing_run_id == claim.processing_run_id,
                    ProcessingJob.step_name == "entry_pipeline",
                )
                .one_or_none()
            )
            if job and job.result_json:
                payload = json.loads(job.result_json)
                payload["replayed"] = True
                payload["idempotency_key"] = key
                return payload
        return {
            "status": claim.status,
            "idempotency_key": key,
            "replayed": True,
            "processing_run_id": claim.processing_run_id,
        }

    def _upsert_job(
        self, user_id: str, entry_id: str, processing_run_id: str
    ) -> ProcessingJob:
        job = ProcessingJob(
            user_id=user_id,
            entry_id=entry_id,
            step_name="entry_pipeline",
            processing_run_id=processing_run_id,
            status="processing",
        )
        self.db.add(job)
        self.db.flush()
        return job

    def _create_attempt(
        self,
        processing_job_id: str,
        attempt_number: int,
        *,
        status: str,
        error_code: str | None = None,
    ) -> None:
        self.db.add(
            ProcessingJobAttempt(
                processing_job_id=processing_job_id,
                attempt_number=attempt_number,
                status=status,
                error_code=error_code,
            )
        )
        self.db.flush()

    def _mark_claim_completed(self, user_id: str, key: str) -> None:
        claim = (
            self.db.query(EntryIdempotencyClaim)
            .filter(
                EntryIdempotencyClaim.user_id == user_id,
                EntryIdempotencyClaim.idempotency_key == key,
            )
            .one()
        )
        claim.status = "completed"

    def _record_failure(
        self,
        *,
        job_id: str,
        user_id: str,
        entry_id: str,
        key: str,
        processing_run_id: str,
        error: str,
        error_code: str,
    ) -> None:
        job = (
            self.db.query(ProcessingJob)
            .filter(ProcessingJob.id == job_id)
            .one_or_none()
        )
        if job is not None:
            job.status = "failed"
            job.last_error_code = error_code
            self.db.add(job)
            self._create_attempt(job.id, 2, status="failed", error_code=error_code)

        claim = (
            self.db.query(EntryIdempotencyClaim)
            .filter(
                EntryIdempotencyClaim.user_id == user_id,
                EntryIdempotencyClaim.idempotency_key == key,
            )
            .one_or_none()
        )
        if claim is None:
            claim = EntryIdempotencyClaim(
                user_id=user_id,
                idempotency_key=key,
                entry_id=entry_id,
                processing_run_id=processing_run_id,
                status="failed",
            )
            self.db.add(claim)
        else:
            claim.status = "failed"

        entry = self._get_entry(user_id=user_id, entry_id=entry_id)
        if entry is not None:
            entry.status = "failed"
            entry.error_message = error
            entry.processed_at = _now_utc()

        self._emit_outbox_event(
            user_id=user_id,
            event_type="entry.processing_failed",
            payload={
                "error": error,
                "error_code": error_code,
                "job_id": job_id,
                "processing_run_id": processing_run_id,
            },
        )
        self.db.commit()

    def _emit_outbox_event(
        self, *, user_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        dedupe_raw = f"{user_id}:{event_type}:{json.dumps(payload, sort_keys=True)}"
        dedupe = hashlib.sha256(dedupe_raw.encode("utf-8")).hexdigest()

        existing = (
            self.db.query(OutboxEvent)
            .filter(OutboxEvent.event_dedupe_key == dedupe)
            .one_or_none()
        )
        if existing is not None:
            return

        self.db.add(
            OutboxEvent(
                user_id=user_id,
                event_type=event_type,
                event_dedupe_key=dedupe,
                payload_json=json.dumps(payload, sort_keys=True),
                status="pending",
            )
        )
        self.db.flush()

    def _save_to_recovery(
        self,
        *,
        entry_id: str,
        user_id: str,
        idempotency_key: str,
        error: str,
        error_code: str,
    ) -> None:
        """Persist a failed entry to the file-based recovery queue.

        Called when normal DB-based failure recording (``_record_failure``)
        is itself unavailable — typically because the database is completely
        down.  Uses the file-based ``RecoveryQueue`` as a last-resort buffer
        so no entry is silently lost.

        If no ``RecoveryQueue`` is configured, logs a CRITICAL warning so the
        operator is alerted that manual intervention may be needed.
        """
        if self.recovery is None:
            logger.critical(
                "pipeline no recovery_queue configured — entry=%s user=%s will NOT be"
                " recoverable automatically. error_code=%s original_error=%s",
                entry_id,
                user_id,
                error_code,
                error[:300],
            )
            return
        try:
            self.recovery.save_failed_entry(
                entry_id=entry_id,
                user_id=user_id,
                idempotency_key=idempotency_key,
                error=error,
                error_code=error_code,
                pipeline_version=PIPELINE_VERSION,
            )
        except Exception as exc:
            logger.critical(
                "pipeline recovery_queue write also failed entry=%s error=%s",
                entry_id,
                exc,
            )

    def _get_entry(self, *, user_id: str, entry_id: str) -> JournalEntry | None:
        return (
            self.db.query(JournalEntry)
            .filter(JournalEntry.user_id == user_id, JournalEntry.id == entry_id)
            .one_or_none()
        )


# ---------------------------------------------------------------------------
# JournalEntryPipeline — async public facade
# ---------------------------------------------------------------------------


class JournalEntryPipeline:
    """Async public facade over ``PipelineProcessor``.

    This is the intended entry point for FastAPI route handlers and
    background workers.  It runs ``PipelineProcessor`` on the default
    thread-pool executor so the asyncio event loop is never blocked by
    synchronous database or HTTP I/O.

    Idempotency key derivation
    --------------------------
    When no *idempotency_key* is provided, one is derived deterministically
    from ``(user_id, entry_id, PIPELINE_VERSION)`` using SHA-256.  This
    means every (user, entry) pair is automatically processed exactly once
    per pipeline version — no caller bookkeeping required.

    Graceful degradation
    --------------------
    - **Ollama unavailable**: embedding (step 05) and insights (step 14b)
      degrade silently; signal detection (step 07) falls back to rule-based
      keyword matching.
    - **Qdrant unavailable**: RAG search (step 06) returns empty context;
      processing continues without evidence-based recommendations.
    - **DB unavailable**: critical failure path — the entry is saved to a
      file-based ``RecoveryQueue`` so it can be retried when the DB recovers.
      Use ``check_services_health()`` as a pre-flight gate.

    Usage (FastAPI)::

        pipeline = JournalEntryPipeline(db_session=db)
        result = await pipeline.process_entry(entry_id, user_id)

    Usage (background worker)::

        pipeline = JournalEntryPipeline(
            db_session=db,
            ollama_client=my_ollama,
            qdrant_client=my_qdrant,
        )
        result = await pipeline.process_entry(
            entry_id, user_id, idempotency_key="worker-run-xyz"
        )

    Pre-flight health check::

        health = await pipeline.check_services_health()
        if health["degraded"]:
            logger.warning("Running in degraded mode: %s", health)
    """

    def __init__(
        self,
        db_session: Session,
        ollama_client: OllamaClient | None = None,
        qdrant_client: QdrantClientAdapter | None = None,
        cache: StepCache | None = None,
        recovery: RecoveryQueue | None = None,
    ) -> None:
        """Initialise the facade and its underlying ``PipelineProcessor``.

        Args:
            db_session:     SQLAlchemy session (must outlive the pipeline call).
            ollama_client:  Optional OllamaClient; a default is created if omitted.
            qdrant_client:  Optional QdrantClientAdapter; a default is created if omitted.
            cache:          Optional StepCache for embedding results.
            recovery:       Optional RecoveryQueue for file-based failure persistence.
                            When omitted, a default queue writing to
                            ``data/recovery/`` is created automatically.
        """
        try:
            self._recovery: RecoveryQueue = recovery or RecoveryQueue()
        except Exception as exc:
            logger.warning(
                "pipeline could not initialise RecoveryQueue (entry data may be"
                " lost on DB failure): %s",
                exc,
            )
            # Provide a non-functional sentinel so type checks elsewhere pass.
            self._recovery = recovery  # type: ignore[assignment]

        self._processor = PipelineProcessor(
            db=db_session,
            ollama=ollama_client,
            qdrant=qdrant_client,
            cache=cache,
            recovery=self._recovery,
        )

    # ------------------------------------------------------------------
    # Pre-flight health check
    # ------------------------------------------------------------------

    async def check_services_health(self) -> dict[str, Any]:
        """Pre-flight health check for Ollama and Qdrant.

        Runs both probes concurrently on the thread-pool so the event loop
        is not blocked.  Never raises — failures are reported in the result.

        Returns:
            Dict with keys:

            ``ollama``       — True if Ollama HTTP endpoint is reachable.
            ``ollama_model`` — True if the configured model is loaded.
            ``qdrant``       — True if Qdrant collection is accessible.
            ``degraded``     — True if *any* AI service is unavailable.
        """
        loop = asyncio.get_running_loop()

        # Ollama: use the sync health() method (never raises, returns structured dict).
        ollama_future = loop.run_in_executor(None, self._processor.ollama.health)

        # Qdrant: probe via ensure_collection(); detect _NoQdrant sentinel.
        def _qdrant_probe() -> bool:
            qdrant = self._processor.qdrant
            if not isinstance(qdrant, QdrantClientAdapter):
                # _NoQdrant sentinel — real Qdrant was unavailable at startup.
                return False
            try:
                qdrant.ensure_collection()
                return True
            except Exception as exc:
                logger.warning("pipeline qdrant health probe failed: %s", exc)
                return False

        qdrant_future = loop.run_in_executor(None, _qdrant_probe)

        ollama_health, qdrant_ok = await asyncio.gather(ollama_future, qdrant_future)
        ollama_ok = bool(ollama_health.get("connected"))

        logger.info(
            "pipeline services_health ollama=%s ollama_model=%s qdrant=%s",
            ollama_ok,
            bool(ollama_health.get("model_available")),
            qdrant_ok,
        )
        return {
            "ollama": ollama_ok,
            "ollama_model": bool(ollama_health.get("model_available")),
            "qdrant": qdrant_ok,
            "degraded": not (ollama_ok and qdrant_ok),
        }

    # ------------------------------------------------------------------
    # Rule-based fallback utility
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_based_activity_extraction(raw_text: str) -> list[dict[str, Any]]:
        """Extract structured activities using keyword + duration pattern matching.

        This is the rule-based fallback for when Ollama is unavailable.  It
        returns the same schema as ``OllamaClient.extract_activities()`` so
        callers are agnostic to which path was taken.

        The function scans for known activity keywords and pairs each match
        with the first duration expression (``"2 hours"``, ``"30 minutes"``)
        found anywhere in the text.  When no duration is found, 30 minutes
        is assumed.

        Args:
            raw_text: Raw journal entry text (not yet normalised).

        Returns:
            List of activity dicts, each with:
            ``activity``         — Capitalised activity label.
            ``duration_minutes`` — Estimated duration as an integer.
            ``notes``            — Provenance note for traceability.
        """
        import re

        lowered = raw_text.lower()

        # Activity keyword registry — extend here without touching callers.
        _ACTIVITY_KEYWORDS: dict[str, list[str]] = {
            "coding": [
                "coded",
                "coding",
                "programming",
                "python",
                "javascript",
                "code",
                "dev",
            ],
            "running": ["ran", "running", "jogged", "jogging", "sprint"],
            "reading": ["read", "reading", "book", "article", "chapter"],
            "writing": ["wrote", "writing", "journaled", "journaling", "drafted"],
            "exercise": [
                "workout",
                "exercised",
                "gym",
                "lifted",
                "weights",
                "training",
            ],
            "meditation": ["meditated", "meditation", "mindfulness", "breathing"],
            "studying": ["studied", "studying", "study", "revision", "flashcard"],
            "walking": ["walked", "walking", "strolled", "hike", "hiking"],
        }

        # Duration pattern: captures value + unit.
        _DURATION_RE = re.compile(
            r"(\d+(?:\.\d+)?)\s*(hour|hr|minute|min)s?", re.IGNORECASE
        )

        # Find the first duration mention in the whole text (best-effort).
        duration_minutes: int = 30  # default when no duration found
        match = _DURATION_RE.search(lowered)
        if match:
            value_str, unit = match.group(1), match.group(2).lower()
            value = float(value_str)
            duration_minutes = int(value * 60) if unit.startswith("h") else int(value)

        activities: list[dict[str, Any]] = []
        for activity_label, keywords in _ACTIVITY_KEYWORDS.items():
            if any(kw in lowered for kw in keywords):
                activities.append(
                    {
                        "activity": activity_label.capitalize(),
                        "duration_minutes": duration_minutes,
                        "notes": "Detected via rule-based fallback (Ollama unavailable)",
                    }
                )

        return activities

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_entry(
        self,
        entry_id: str,
        user_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Process a journal entry asynchronously through all 17 steps.

        Dispatches ``PipelineProcessor.process_entry`` to the default thread-
        pool executor so the calling coroutine is not blocked.

        Graceful degradation
        --------------------
        - Ollama / Qdrant unavailable → affected steps degrade individually;
          the pipeline still completes and persists XP / quest progress.
        - DB unavailable during setup (idempotency claim, job creation) →
          critical failure; entry is saved to the ``RecoveryQueue`` so it can
          be retried when the DB recovers.  ``PipelineStepError`` raised inside
          ``_run_steps`` already routes through ``_record_failure`` which also
          saves to recovery when the DB commit fails there.

        Args:
            entry_id:         Journal entry UUID.
            user_id:          Owning user UUID.
            idempotency_key:  Optional caller-supplied dedup key.  When
                              omitted, a deterministic key is derived from
                              ``(user_id, entry_id, PIPELINE_VERSION)``.

        Returns:
            Processing result dict — see ``PipelineProcessor.process_entry``.

        Raises:
            PipelineStepError: When a mandatory step fails irrecoverably.
            Exception:         Propagated from the processor for any other
                               failure; entry is saved to recovery queue first.
        """
        key = idempotency_key or _derive_idempotency_key(user_id, entry_id)
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None,
                functools.partial(
                    self._processor.process_entry, entry_id, user_id, key
                ),
            )
        except PipelineStepError:
            # PipelineProcessor already called _record_failure() (and _save_to_recovery()
            # if the DB was down at that point).  Nothing more to do here.
            raise
        except Exception as exc:
            # An exception escaped *before* PipelineProcessor's own error handler ran —
            # typically the DB was unreachable during the setup phase (idempotency
            # claim, job creation, initial commit).  Save to the recovery queue so the
            # entry is not silently lost.
            logger.critical(
                "pipeline setup-phase failure entry=%s user=%s error=%s"
                " — saving to recovery queue",
                entry_id,
                user_id,
                exc,
            )
            if self._recovery is not None:
                try:
                    self._recovery.save_failed_entry(
                        entry_id=entry_id,
                        user_id=user_id,
                        idempotency_key=key,
                        error=str(exc),
                        error_code="SETUP_EXCEPTION",
                        pipeline_version=PIPELINE_VERSION,
                    )
                except Exception as queue_exc:
                    logger.critical(
                        "pipeline facade recovery_queue write failed entry=%s: %s",
                        entry_id,
                        queue_exc,
                    )
            raise
