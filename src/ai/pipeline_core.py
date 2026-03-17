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
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import functools
import hashlib
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from src.ai.cache import StepCache
from src.ai.ollama import OllamaClient
from src.ai.qdrant import QdrantClientAdapter
from src.ai.recovery import RecoveryQueue
from src.ai.tx_guard import forbid_network_calls

# Step modules — each encapsulates the business logic for one or more steps.
from src.ai.steps import anomaly as _s_anomaly
from src.core.anomaly_orchestrator import AnomalyOrchestrator
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

from src.ai.pipeline_steps.quest_matcher_step import QuestMatcherStep
from src.core.arc_lifecycle import ArcLifecycleService
from src.core.arc_recovery_detection import RecoveryDetectionService
from src.core.arc_regression_trigger import RegressionTriggerService
from src.core.arc_vacation import VacationModeService
from src.core.entry_skill_resolver import resolve_entry_skill_signals
from src.core.forgiveness_decay_service import ForgivenessDecayService
from src.core.harmony_classifier import HarmonyClassifier
from src.core.harmony_refresh_service import HarmonyRefreshService
from src.core.personality_message_persistence import MessagePersistenceService
from src.core.personality_message_serialization import serialize_personality_messages
from src.core.personality_orchestrator import PersonalityOrchestrator
from src.db.models.global_kb import GlobalSkill
from src.db.models.journal_entry import JournalEntry, JournalEntryStructured
from src.db.models.personality import PersonalityMessage
from src.db.models.quest import Quest
from src.db.models.server_config import ServerConfig
from src.db.models.skill import Skill
from src.db.models.skill import Theme
from src.db.models.user import User
from src.db.models.processing import (
    EntryIdempotencyClaim,
    OutboxEvent,
    ProcessingJob,
    ProcessingJobAttempt,
)
from src.db.models.processing_distributed import ProcessingJobClaim

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "week3-v2"
RULESET_VERSION = "s10-v8"


def _compat_pipeline_attr(name: str, default: Any) -> Any:
    """Resolve legacy patch points from ``src.ai.pipeline`` when available."""
    pipeline_module = sys.modules.get("src.ai.pipeline")
    return getattr(pipeline_module, name, default) if pipeline_module else default


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


def _hash_json_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_hex(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _safe_local_event_date(tz_name: str, created_at_utc: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
    return created_at_utc.astimezone(tz).date().isoformat()


def _config_version() -> str:
    return "config-v1"


def _derive_week7_structured_signals(
    *,
    user_id: str,
    canonical_text: str,
    detection: dict[str, Any],
    db: Session,
) -> dict[str, Any]:
    resolution = resolve_entry_skill_signals(
        user_id=user_id,
        canonical_text=canonical_text,
        detected_skills=detection.get("detected_skills", []),
        detected_activities=detection.get("detected_activities", []),
        detected_global_skill_ids=detection.get("detected_global_skills", []),
        detected_skill_weights=detection.get("skills_weights", {}),
        detected_global_skill_weights=detection.get("global_skills_weights", {}),
        db=db,
    )
    return {
        "source_skills_weights_bp": resolution.source_skills_weights_bp,
        "skills_weights_bp": resolution.skills_weights_bp,
        "resolved_skill_names": resolution.resolved_skill_names,
        "extraction_confidence_score": resolution.extraction_confidence_score,
        "pattern_hits_json": resolution.pattern_hits_json,
    }


def _pick_primary_personality_message(
    serialized_messages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for message in serialized_messages:
        multi = message.get("multi_personality")
        if isinstance(multi, dict) and bool(multi.get("is_primary", False)):
            return message
    return serialized_messages[0] if serialized_messages else None


@dataclass
class ErrorRecord:
    step: str
    code: str
    category: str
    retryable: bool
    severity: str
    message: str
    internal_details: dict[str, Any] | None = None


@dataclass
class VersionSnapshot:
    pipeline_version: str
    ruleset_version: str
    config_version: str
    parser_version: str
    timezone_rules_version: str
    ai_models: dict[str, str]
    prompt_versions: dict[str, str]
    ai_params: dict[str, dict[str, Any]]


@dataclass
class TimeSnapshot:
    created_at_utc: str
    processing_started_at_utc: str
    processing_completed_at_utc: str | None
    user_timezone_at_ingest: str
    local_event_date: str


@dataclass
class StepMetrics:
    step_name: str
    attempt: int
    duration_ms: int
    status: Literal["succeeded", "failed_critical", "fallback", "suppressed"]
    error_code: str | None = None
    critical: bool = False
    fallback_used: bool = False
    not_persisted_reason: str | None = None


@dataclass
class PipelineContext:
    entry_id: str
    user_id: str
    request: dict[str, Any]
    idempotency_key_normalized: str
    processing_run_id: str
    job_id: str
    attempt_id: int
    logical_step_name: str
    entry_status: str
    versions: VersionSnapshot
    time: TimeSnapshot
    step_metrics: list[StepMetrics] = field(default_factory=list)
    noncritical_errors: list[ErrorRecord] = field(default_factory=list)
    terminal_error: ErrorRecord | None = None
    outputs: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntryProcessingSuccessResult:
    result_type: Literal["success"] = "success"
    entry_id: str = ""
    user_id: str = ""
    created_at_utc: str = ""
    processing_started_at_utc: str = ""
    processing_completed_at_utc: str = ""
    local_event_date: str = ""
    status: Literal["completed"] = "completed"
    structured_data: dict[str, Any] = field(default_factory=dict)
    quests_created: list[dict[str, Any]] = field(default_factory=list)
    quests_completed: list[dict[str, Any]] = field(default_factory=list)
    quests_progressed: list[dict[str, Any]] = field(default_factory=list)
    xp_awards: list[dict[str, Any]] = field(default_factory=list)
    level_ups: list[dict[str, Any]] = field(default_factory=list)
    skill_updates: list[dict[str, Any]] = field(default_factory=list)
    theme_updates: list[dict[str, Any]] = field(default_factory=list)
    harmony_status: dict[str, Any] = field(default_factory=dict)
    strategy_detected: str | None = None
    variety_bonus: float = 0.0
    insights_discovered: list[dict[str, Any]] = field(default_factory=list)
    arc_updates: list[dict[str, Any]] = field(default_factory=list)
    anomaly_score: float = 0.0
    troll_multiplier: float = 1.0
    personality_messages: list[dict[str, Any]] = field(default_factory=list)
    active_personality: str | None = None
    processing_duration_ms: int = 0
    steps_attempted: int = 0
    steps_succeeded: int = 0
    steps_fallbacked: int = 0
    noncritical_errors: list[dict[str, Any]] = field(default_factory=list)
    pipeline_version: str = ""
    ruleset_version: str = ""
    config_version: str = ""
    processing_run_id: str = ""
    job_id: str = ""
    poll_path: str = ""
    summary: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    message_id: str | None = None
    personality: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    step_trace: list[dict[str, Any]] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    insight_result: dict[str, Any] = field(default_factory=dict)
    personality_result: dict[str, Any] = field(default_factory=dict)
    report_result: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntryProcessingFailureResult:
    result_type: Literal["failure"] = "failure"
    entry_id: str | None = None
    user_id: str = ""
    created_at_utc: str | None = None
    processing_started_at_utc: str = ""
    processing_completed_at_utc: str = ""
    local_event_date: str | None = None
    status: Literal["failed"] = "failed"
    terminal_error: dict[str, Any] = field(default_factory=dict)
    noncritical_errors: list[dict[str, Any]] = field(default_factory=list)
    processing_duration_ms: int = 0
    pipeline_version: str = ""
    ruleset_version: str = ""
    config_version: str = ""
    processing_run_id: str | None = None
    retry_allowed: bool = False
    retry_after_ms: int | None = None
    job_id: str | None = None
    poll_path: str | None = None
    step_trace: list[dict[str, Any]] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntryProcessingAckResult:
    result_type: Literal["ack"] = "ack"
    status: Literal["pending", "in_progress"] = "pending"
    job_id: str = ""
    entry_id: str | None = None
    user_id: str = ""
    processing_run_id: str = ""
    poll_path: str = ""
    idempotency_key: str = ""
    retryable: bool = True
    created_at_utc: str | None = None
    updated_at_utc: str | None = None
    attempt_count: int = 0
    last_error_code: str | None = None


# ---------------------------------------------------------------------------
# Private step helpers — called from within _run_steps lambdas
# ---------------------------------------------------------------------------


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return _iso8601z(value)
    return str(value)


def _store_step_output(ctx: PipelineContext, step_name: str, value: Any) -> None:
    ctx.outputs.setdefault("step_outputs", {})[step_name] = _json_safe(value)


def _record_manual_step(
    *,
    ctx: PipelineContext,
    step_name: str,
    duration_ms: int,
    output: Any,
    critical: bool,
    not_persisted_reason: str | None = None,
) -> None:
    _store_step_output(ctx, step_name, output)
    ctx.step_metrics.append(
        StepMetrics(
            step_name=step_name,
            attempt=ctx.attempt_id,
            duration_ms=duration_ms,
            status="succeeded",
            critical=critical,
            fallback_used=False,
            not_persisted_reason=not_persisted_reason,
        )
    )


def _build_step_trace(
    ctx: PipelineContext,
    *,
    quality: dict[str, Any],
) -> list[dict[str, Any]]:
    outputs = ctx.outputs.get("step_outputs", {})
    traces: list[dict[str, Any]] = []
    for metric in ctx.step_metrics:
        output = outputs.get(metric.step_name)
        status = metric.status
        if status == "succeeded" and isinstance(output, dict) and output.get(
            "suppression_reason"
        ):
            status = "suppressed"
        traces.append(
            {
                "step_name": metric.step_name,
                "status": status,
                "duration_ms": metric.duration_ms,
                "critical": metric.critical,
                "fallback_used": metric.fallback_used,
                "error_code": metric.error_code,
                "error_message": next(
                    (
                        err.message
                        for err in ctx.noncritical_errors
                        if err.step == metric.step_name and err.code == metric.error_code
                    ),
                    ctx.terminal_error.message
                    if ctx.terminal_error is not None
                    and ctx.terminal_error.step == metric.step_name
                    and ctx.terminal_error.code == metric.error_code
                    else None,
                ),
                "output": output,
                "not_persisted_reason": metric.not_persisted_reason,
            }
        )
    return traces


def _build_quality_payload(
    ctx: PipelineContext,
    *,
    cache_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    step_outputs = ctx.outputs.get("step_outputs", {})
    degraded_codes = sorted(
        {
            metric.error_code
            for metric in ctx.step_metrics
            if metric.status == "fallback" and metric.error_code
        }
        | {
            str((step_outputs.get(metric.step_name) or {}).get("suppression_reason"))
            for metric in ctx.step_metrics
            if metric.status == "suppressed"
            and isinstance(step_outputs.get(metric.step_name), dict)
            and (step_outputs.get(metric.step_name) or {}).get("suppression_reason")
        }
    )
    ollama_health = step_outputs.get("step_04_ollama_health", {})
    rag_result = step_outputs.get("step_06_rag_search", {})
    dependency_states = {
        "ollama": {
            "connected": bool(ollama_health.get("connected")),
            "error_code": None
            if ollama_health.get("connected")
            else "DEPENDENCY_OLLAMA_UNAVAILABLE",
        },
        "qdrant": {
            "connected": not bool(rag_result.get("error")),
            "error_code": "DEPENDENCY_QDRANT_UNAVAILABLE"
            if rag_result.get("error")
            else None,
        },
    }
    if not rag_result.get("hits"):
        dependency_states["rag"] = {
            "connected": bool(rag_result) and not bool(rag_result.get("error")),
            "error_code": "RAG_EMPTY_CONTEXT",
        }
    else:
        dependency_states["rag"] = {"connected": True, "error_code": None}
    return {
        "degraded": bool(degraded_codes),
        "degraded_codes": degraded_codes,
        "dependency_states": dependency_states,
        "cache_stats": cache_stats or {},
    }


def _build_provenance_payload(
    ctx: PipelineContext,
    *,
    quality: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pipeline_version": ctx.versions.pipeline_version,
        "ruleset_version": ctx.versions.ruleset_version,
        "config_version": ctx.versions.config_version,
        "parser_version": ctx.versions.parser_version,
        "timezone_rules_version": ctx.versions.timezone_rules_version,
        "ai_models": _json_safe(ctx.versions.ai_models),
        "prompt_versions": _json_safe(ctx.versions.prompt_versions),
        "ai_params": _json_safe(ctx.versions.ai_params),
        "request": _json_safe(ctx.request),
        "idempotency_key": ctx.idempotency_key_normalized,
        "processing_run_id": ctx.processing_run_id,
        "quality_codes": list(quality.get("degraded_codes", [])),
    }


def _build_safety_result(detection: dict[str, Any]) -> dict[str, Any]:
    """Derive a personality-system safety_result from signal detection output.

    Maps energy_level, self_compassion_score and dominant_emotions to the
    ``{force_therapist, risk_level, sentiment_score}`` shape expected by
    PersonalitySelector and PersonalityMessageGenerator.
    """
    energy: int = int(detection.get("energy_level", 5))
    compassion: int = int(detection.get("self_compassion_score", 7))
    emotions: list[str] = [
        str(e).lower() for e in detection.get("dominant_emotions", [])
    ]

    negative_emotions = {"sad", "anxious", "angry", "depressed", "stressed", "hopeless"}
    is_negative = any(e in negative_emotions for e in emotions)

    force_therapist = energy < 3 and is_negative
    if energy < 2:
        risk_level = "crisis"
    elif energy < 4 and is_negative:
        risk_level = "warning"
    else:
        risk_level = "none"

    # Blend energy (0-10 → 0-50) and compassion (0-10 → 0-50) into 0-100
    sentiment_score = int((energy / 10.0) * 50 + (compassion / 10.0) * 50)

    return {
        "force_therapist": force_therapist,
        "risk_level": risk_level,
        "sentiment_score": sentiment_score,
    }


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


def build_extraction_fallback(
    error_code: str,
    versions: VersionSnapshot,
    now_utc_iso: str,
) -> dict[str, Any]:
    """Deterministic non-null structured fallback object."""
    return {
        "canonical_text": "",
        "task_type": "unknown",
        "energy_level": None,
        "dominant_emotions": [],
        "self_compassion_score": None,
        "skills_themes_involved": [],
        "safety_flags": [],
        "source_skills_weights_bp": {},
        "skills_weights_bp": {},
        "resolved_skill_names": [],
        "extraction_confidence_score": 0.0,
        "pattern_hits_json": [],
        "extraction_status": "failed",
        "extraction_error_code": error_code,
        "parser_version": versions.parser_version,
        "extracted_at": now_utc_iso,
    }


# ---------------------------------------------------------------------------
# PipelineProcessor — synchronous orchestrator
# ---------------------------------------------------------------------------


class PipelineProcessor:
    """Canonical Section 13 entry processor with explicit Tx A / outside-Tx / Tx B."""

    def __init__(
        self,
        db: Session,
        ollama: OllamaClient | None = None,
        qdrant: QdrantClientAdapter | None = None,
        cache: StepCache | None = None,
        recovery: RecoveryQueue | None = None,
    ) -> None:
        self.db = db
        ollama_cls = _compat_pipeline_attr("OllamaClient", OllamaClient)
        cache_cls = _compat_pipeline_attr("StepCache", StepCache)
        self.ollama = ollama or ollama_cls()
        self.qdrant = qdrant or self._build_default_qdrant()
        self.cache = cache or cache_cls(ttl_hours=24)
        self.recovery = recovery
        self._strict_ai_dependencies = os.getenv("STRICT_AI_DEPENDENCIES", "0")
        self._active_db: Session | None = None
        bind = self.db.get_bind() if hasattr(self.db, "get_bind") else None
        self._session_factory = (
            sessionmaker(
                bind=bind,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )
            if bind is not None
            else None
        )

    @staticmethod
    def _build_default_qdrant() -> Any:
        try:
            qdrant_cls = _compat_pipeline_attr(
                "QdrantClientAdapter", QdrantClientAdapter
            )
            return qdrant_cls()
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
        self,
        entry_id: str,
        user_id: str,
        idempotency_key: str,
        *,
        job_id: str | None = None,
        processing_run_id: str | None = None,
        reserved_claim: bool = False,
        request_payload_hash: str | None = None,
    ) -> dict[str, Any]:
        """Process a journal entry with canonical transaction boundaries."""
        normalized_key = (idempotency_key or "").strip()
        if not normalized_key:
            raise PipelineStepError(
                "step_03_idempotency",
                "VALIDATION_INVALID_INPUT",
                "idempotency_key must not be empty",
            )
        if self._session_factory is None:
            raise RuntimeError("PipelineProcessor requires a SQLAlchemy session")

        logger.info(
            "[pipeline:trace] start entry=%s user=%s idempotency=%s reserved_claim=%s",
            entry_id,
            user_id,
            normalized_key,
            reserved_claim,
        )
        try:
            if not reserved_claim:
                replay = self._get_idempotent_replay(user_id, normalized_key)
                if replay is not None:
                    return replay

            ctx = self._tx_a_initialize(
                entry_id=entry_id,
                user_id=user_id,
                idempotency_key=normalized_key,
                job_id=job_id,
                processing_run_id=processing_run_id,
                reserved_claim=reserved_claim,
                request_payload_hash=request_payload_hash,
            )
            replay_payload = ctx.outputs.get("replay_payload")
            if isinstance(replay_payload, dict):
                return replay_payload
            _record_manual_step(
                ctx=ctx,
                step_name="step_01_validate_input",
                duration_ms=0,
                output={
                    "user_id": user_id,
                    "entry_id": entry_id,
                    "idempotency_key": normalized_key,
                },
                critical=True,
                not_persisted_reason="validation-only step",
            )
            plan = self._plan_outside_tx(ctx)
            result = self._apply_tx_b(ctx, plan, idempotency_key=normalized_key)
            self._dispatch_outbox_for_run(ctx.processing_run_id)
            logger.info(
                "pipeline completed run=%s user=%s entry=%s idempotency=%s",
                ctx.processing_run_id,
                user_id,
                entry_id,
                normalized_key,
            )
            return result
        except Exception as exc:
            ctx = locals().get("ctx")
            error_code = (
                exc.error_code
                if isinstance(exc, PipelineStepError)
                else "PIPELINE_EXCEPTION"
            )
            if ctx is None:
                raise
            failure_result = self._build_failure_result(
                ctx=ctx,
                error_code=error_code,
                message=str(exc),
            )
            try:
                self._record_failure(
                    job_id=ctx.job_id,
                    user_id=user_id,
                    entry_id=entry_id,
                    key=normalized_key,
                    processing_run_id=ctx.processing_run_id,
                    request_payload_hash=request_payload_hash,
                    error=str(exc),
                    error_code=error_code,
                    failure_payload=failure_result,
                    attempt_id=ctx.attempt_id,
                )
            except Exception as record_exc:
                logger.critical(
                    "pipeline failure_recording failed run=%s entry=%s record_error=%s"
                    " - saving to recovery queue",
                    ctx.processing_run_id,
                    entry_id,
                    record_exc,
                )
                self._save_to_recovery(
                    entry_id=entry_id,
                    user_id=user_id,
                    idempotency_key=normalized_key,
                    error=str(exc),
                    error_code=error_code,
                )
            raise
        finally:
            self._expire_caller_session()

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _new_session(self):
        if self._session_factory is None:
            yield self.db
            return
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    @contextmanager
    def _use_db(self, db: Session):
        previous = self._active_db
        self._active_db = db
        try:
            yield
        finally:
            self._active_db = previous

    def _db_handle(self) -> Session:
        db = self._active_db or self.db
        if not hasattr(db, "query"):
            raise RuntimeError("Active pipeline DB handle is not a SQLAlchemy session")
        return db

    def _expire_caller_session(self) -> None:
        if hasattr(self.db, "expire_all"):
            try:
                self.db.expire_all()
            except Exception:
                return

    # ------------------------------------------------------------------
    # Tx A / planning / Tx B
    # ------------------------------------------------------------------

    def _freeze_versions(self) -> VersionSnapshot:
        model_name = getattr(self.ollama, "model", "unknown")
        return VersionSnapshot(
            pipeline_version=PIPELINE_VERSION,
            ruleset_version=RULESET_VERSION,
            config_version=_config_version(),
            parser_version="normalize-v1",
            timezone_rules_version="iana-v1",
            ai_models={
                "extraction": model_name,
                "insight": model_name,
                "personality": model_name,
                "rag": getattr(self.qdrant, "collection", "rag_documents"),
            },
            prompt_versions={
                "extraction": "structured-v1",
                "insight": "insight-v1",
                "personality": "personality-v3.2",
            },
            ai_params={
                "embedding": {"cache_ttl_hours": 24},
                "rag": {"limit": 5},
            },
        )

    def _tx_a_initialize(
        self,
        *,
        entry_id: str,
        user_id: str,
        idempotency_key: str,
        job_id: str | None,
        processing_run_id: str | None,
        reserved_claim: bool,
        request_payload_hash: str | None,
    ) -> PipelineContext:
        with self._new_session() as db, self._use_db(db):
            processing_run_id = processing_run_id or str(uuid.uuid4())
            versions = self._freeze_versions()

            entry = self._get_entry(user_id=user_id, entry_id=entry_id)
            if entry is None:
                raise PipelineStepError(
                    "step_01_validate_input",
                    "ENTRY_NOT_FOUND",
                    f"journal entry {entry_id} for user {user_id} not found",
                )

            user = db.query(User).filter(User.id == user_id).one_or_none()
            if user is None:
                raise PipelineStepError(
                    "step_01_validate_input",
                    "USER_NOT_FOUND",
                    f"user {user_id} not found",
                )

            now = _now_utc()
            created_at = entry.created_at or now
            user_timezone = user.timezone or "UTC"
            time_snapshot = TimeSnapshot(
                created_at_utc=_iso8601z(created_at),
                processing_started_at_utc=_iso8601z(now),
                processing_completed_at_utc=None,
                user_timezone_at_ingest=user_timezone,
                local_event_date=_safe_local_event_date(user_timezone, created_at),
            )

            if reserved_claim:
                job = self._get_job(job_id=job_id, user_id=user_id)
                if job is None:
                    raise PipelineStepError(
                        "step_04_create_job",
                        "JOB_NOT_FOUND",
                        f"reserved processing job {job_id} not found for user {user_id}",
                    )
                claim = self._mark_claim_in_progress(
                    user_id=user_id,
                    key=idempotency_key,
                    entry_id=entry_id,
                    processing_job_id=job.id,
                    processing_run_id=processing_run_id,
                    request_payload_hash=request_payload_hash,
                )
            else:
                try:
                    self._claim_idempotency(
                        user_id,
                        entry_id,
                        idempotency_key,
                        processing_run_id,
                        request_payload_hash=request_payload_hash,
                    )
                except IntegrityError:
                    db.rollback()
                    replay = self._get_idempotent_replay(user_id, idempotency_key)
                    if replay is not None:
                        return PipelineContext(
                            entry_id=str(replay.get("entry_id") or entry_id),
                            user_id=user_id,
                            request={},
                            idempotency_key_normalized=idempotency_key,
                            processing_run_id=str(
                                replay.get("processing_run_id") or processing_run_id
                            ),
                            job_id=str(replay.get("job_id") or job_id or ""),
                            attempt_id=1,
                            logical_step_name="entry_pipeline",
                            entry_status=str(replay.get("status") or "processing"),
                            versions=versions,
                            time=time_snapshot,
                            outputs={"replay_payload": replay},
                        )
                    raise
                job = self._upsert_job(
                    user_id,
                    entry_id,
                    processing_run_id,
                    job_id=job_id,
                    request_payload_hash=request_payload_hash,
                    versions=versions,
                )
                claim = self._mark_claim_in_progress(
                    user_id=user_id,
                    key=idempotency_key,
                    entry_id=entry_id,
                    processing_job_id=job.id,
                    processing_run_id=processing_run_id,
                    request_payload_hash=request_payload_hash,
                )

            job.status = "in_progress"
            job.request_payload_hash = request_payload_hash
            job.pipeline_version = versions.pipeline_version
            job.ruleset_version = versions.ruleset_version
            job.config_version = versions.config_version
            job.ai_version_snapshot = json.dumps(
                versions.ai_models, sort_keys=True, separators=(",", ":")
            )
            job.prompt_version_snapshot = json.dumps(
                versions.prompt_versions, sort_keys=True, separators=(",", ":")
            )
            entry.status = "processing"
            entry.error_message = None
            self._upsert_claim_lease(
                user_id=user_id,
                entry_id=entry_id,
                step_name="entry_pipeline",
                owner_kind="server_worker",
                owner_id="pipeline",
            )
            claim.result_pointer_json = json.dumps(
                self._terminal_result_pointer(job, status="pending"),
                sort_keys=True,
            )
            claim.updated_at = now
            db.commit()

            return PipelineContext(
                entry_id=entry.id,
                user_id=user_id,
                request={
                    "user_id": user_id,
                    "entry_id": entry.id,
                    "content_type": entry.entry_type,
                    "idempotency_key": idempotency_key,
                },
                idempotency_key_normalized=idempotency_key,
                processing_run_id=job.processing_run_id,
                job_id=job.id,
                attempt_id=max(1, int(job.attempt_count or 0) + 1),
                logical_step_name="entry_pipeline",
                entry_status=entry.status,
                versions=versions,
                time=time_snapshot,
            )

    def _run_step(
        self,
        *,
        ctx: PipelineContext,
        step_name: str,
        error_code: str,
        category: str,
        critical: bool,
        fn: Callable[[], dict[str, Any] | list[Any] | str | None],
        fallback_fn: Callable[[Exception], Any] | None = None,
        retryable: bool = False,
        severity: str = "warning",
    ) -> Any:
        started = time.perf_counter()
        try:
            value = fn()
            _store_step_output(ctx, step_name, value)
            status: Literal["succeeded", "suppressed"] = "succeeded"
            if isinstance(value, dict) and value.get("suppression_reason"):
                status = "suppressed"
            ctx.step_metrics.append(
                StepMetrics(
                    step_name=step_name,
                    attempt=ctx.attempt_id,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    status=status,
                    critical=critical,
                    fallback_used=False,
                )
            )
            return value
        except Exception as exc:
            err = ErrorRecord(
                step=step_name,
                code=error_code,
                category=category,
                retryable=retryable,
                severity=severity,
                message=str(exc),
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            if critical and fallback_fn is None:
                ctx.terminal_error = err
                ctx.step_metrics.append(
                    StepMetrics(
                        step_name=step_name,
                        attempt=ctx.attempt_id,
                        duration_ms=duration_ms,
                        status="failed_critical",
                        error_code=error_code,
                        critical=critical,
                        fallback_used=False,
                    )
                )
                raise PipelineStepError(step_name, error_code, str(exc)) from exc

            ctx.noncritical_errors.append(err)
            if fallback_fn is None:
                ctx.step_metrics.append(
                    StepMetrics(
                        step_name=step_name,
                        attempt=ctx.attempt_id,
                        duration_ms=duration_ms,
                        status="suppressed",
                        error_code=error_code,
                        critical=critical,
                        fallback_used=False,
                    )
                )
                _store_step_output(
                    ctx,
                    step_name,
                    {
                        "suppression_reason": error_code,
                        "error_message": str(exc),
                    },
                )
                return None

            value = fallback_fn(exc)
            _store_step_output(ctx, step_name, value)
            ctx.step_metrics.append(
                StepMetrics(
                    step_name=step_name,
                    attempt=ctx.attempt_id,
                    duration_ms=duration_ms,
                    status="fallback",
                    error_code=error_code,
                    critical=critical,
                    fallback_used=True,
                )
            )
            return value

    def _planned_structured_data(
        self,
        *,
        canonical_text: str,
        detection: dict[str, Any],
        db: Session,
        ctx: PipelineContext,
    ) -> dict[str, Any]:
        try:
            week7_signals = _derive_week7_structured_signals(
                user_id=ctx.user_id,
                canonical_text=canonical_text,
                detection=detection,
                db=db,
            )
            return {
                "canonical_text": canonical_text,
                "primary_action_type": (
                    detection["detected_activities"][0]
                    if detection["detected_activities"]
                    else None
                ),
                "dominant_emotions": list(detection["dominant_emotions"]),
                "energy_level": int(detection["energy_level"]),
                "self_compassion_score": int(detection["self_compassion_score"]),
                "task_type": detection["task_type"],
                "skills_themes_involved": list(
                    week7_signals["resolved_skill_names"]
                    or detection["detected_skills"]
                ),
                "safety_flags": list(detection.get("safety_flags", [])),
                "source_skills_weights_bp": week7_signals[
                    "source_skills_weights_bp"
                ],
                "skills_weights_bp": week7_signals["skills_weights_bp"],
                "resolved_skill_names": week7_signals["resolved_skill_names"],
                "extraction_confidence_score": week7_signals[
                    "extraction_confidence_score"
                ],
                "pattern_hits_json": week7_signals["pattern_hits_json"],
                "extraction_status": "succeeded",
                "parser_version": ctx.versions.parser_version,
                "extracted_at": ctx.time.processing_started_at_utc,
            }
        except Exception:
            return build_extraction_fallback(
                "AI_EXTRACTION_PARSE_FAILED",
                ctx.versions,
                ctx.time.processing_started_at_utc,
            )

    def _plan_outside_tx(self, ctx: PipelineContext) -> dict[str, Any]:
        with self._new_session() as db, self._use_db(db):
            load_started = time.perf_counter()
            entry = self._get_entry(user_id=ctx.user_id, entry_id=ctx.entry_id)
            if entry is None:
                raise PipelineStepError(
                    "step_02_load_entry",
                    "STEP_02_LOAD_ENTRY",
                    f"journal entry {ctx.entry_id} not found during planning",
                )
            _record_manual_step(
                ctx=ctx,
                step_name="step_02_load_entry",
                duration_ms=int((time.perf_counter() - load_started) * 1000),
                output={
                    "entry_id": entry.id,
                    "status": entry.status,
                    "created_at_utc": _iso8601z(entry.created_at) if entry.created_at else None,
                },
                critical=True,
            )

            normalized = self._run_step(
                ctx=ctx,
                step_name="step_03_normalize_text",
                error_code="STEP_03_NORMALIZE",
                category="validation",
                critical=True,
                fn=lambda: _s_normalize.run(entry.content or ""),
            )
            ollama_health = self._run_step(
                ctx=ctx,
                step_name="step_04_ollama_health",
                error_code="STEP_04_OLLAMA_HEALTH",
                category="network",
                critical=False,
                retryable=True,
                fn=lambda: self.ollama.health(),
                fallback_fn=lambda exc: {
                    "connected": False,
                    "model_available": False,
                    "models": [],
                    "error": str(exc),
                    "error_code": "DEPENDENCY_OLLAMA_UNAVAILABLE",
                },
            )
            embedding = self._run_step(
                ctx=ctx,
                step_name="step_05_embedding",
                error_code="STEP_05_EMBEDDING",
                category="ai",
                critical=False,
                retryable=True,
                fn=lambda: _s_embedding.run(
                    entry_id=ctx.entry_id,
                    normalized_text=normalized["canonical_text"],
                    ollama_health=ollama_health,
                    ollama=self.ollama,
                    qdrant=self.qdrant,
                    cache=self.cache,
                ),
                fallback_fn=lambda _exc: {
                    "vector": [],
                    "from_cache": False,
                    "fallback": True,
                },
            )
            rag = self._run_step(
                ctx=ctx,
                step_name="step_06_rag_search",
                error_code="STEP_06_RAG_SEARCH",
                category="network",
                critical=False,
                retryable=True,
                fn=lambda: _s_rag.run(
                    vector=embedding.get("vector", []),
                    qdrant=self.qdrant,
                    cache=self.cache,
                    entry_id=ctx.entry_id,
                ),
                fallback_fn=lambda exc: {
                    "hits": [],
                    "hit_count": 0,
                    "fallback": True,
                    "error": str(exc),
                    "error_code": "DEPENDENCY_QDRANT_UNAVAILABLE",
                },
            )
            detection = self._run_step(
                ctx=ctx,
                step_name="step_07_detect_signals",
                error_code="STEP_07_SIGNAL_DETECTION",
                category="db",
                critical=False,
                retryable=True,
                fn=lambda: _s_signals.run(
                    user_id=ctx.user_id,
                    canonical_text=normalized["canonical_text"],
                    db=db,
                    ollama_health=ollama_health,
                    ollama=self.ollama,
                    rag_hits=rag.get("hits", []),
                    qdrant=self.qdrant,
                ),
                fallback_fn=lambda _exc: {
                    "detected_skills": [],
                    "detected_activities": [],
                    "dominant_emotions": [],
                    "energy_level": 5,
                    "self_compassion_score": 7,
                    "task_type": "unknown",
                    "detected_themes": [],
                    "skills_weights": {},
                    "detected_global_skills": [],
                    "global_skills_weights": {},
                    "certainty": 0.0,
                    "llm_inputs_snapshot": {},
                },
            )

            anomaly_result = self._run_step(
                ctx=ctx,
                step_name="step_08b_anomaly_detection",
                error_code="STEP_08B_ANOMALY_DETECTION",
                category="ai",
                critical=True,
                fn=lambda: self._plan_anomaly(db, ctx, entry),
            )
            strategy_preview = self._run_step(
                ctx=ctx,
                step_name="step_08c_detect_strategies",
                error_code="STEP_08C_STRATEGY_DETECT",
                category="db",
                critical=False,
                retryable=True,
                fn=lambda: _s_strategy.run(
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                    canonical_text=normalized["canonical_text"],
                    detection=detection,
                    anomaly_score=anomaly_result.get("anomaly_score", 0.0),
                    db=db,
                ),
                fallback_fn=lambda _exc: {
                    "detected_strategies": [],
                    "strategy_scores": {},
                    "diminishing_multiplier": 1.0,
                    "diminishing_bp": 10000,
                },
            )
            variety_preview = self._run_step(
                ctx=ctx,
                step_name="step_08a_calculate_variety",
                error_code="STEP_08A_VARIETY",
                category="db",
                critical=False,
                retryable=True,
                fn=lambda: _s_variety.run(user_id=ctx.user_id, db=db),
                fallback_fn=lambda _exc: {
                    "variety_score": 0.0,
                    "variety_bonus_pct": 0.0,
                    "variety_multiplier_bp": 10000,
                    "strategy_counts": {},
                    "window_days": 30,
                },
            )
            harmony_preview = self._run_step(
                ctx=ctx,
                step_name="step_08d_harmony_refresh",
                error_code="STEP_08D_HARMONY_REFRESH",
                category="db",
                critical=False,
                retryable=True,
                fn=lambda: _harmony_step(
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                    entry=entry,
                    db=db,
                ),
                fallback_fn=lambda _exc: {
                    "dimensions_addressed": [],
                    "overall_balance": 0.5,
                    "overwork_stage": 0,
                },
            )
            matched_preview = self._run_step(
                ctx=ctx,
                step_name="step_09_match_quests",
                error_code="STEP_09_QUEST_MATCH",
                category="db",
                critical=True,
                fn=lambda: _s_quests.match(
                    entry=entry,
                    user_id=ctx.user_id,
                    detected_skills=detection["detected_skills"],
                    detected_activities=detection["detected_activities"],
                    db=db,
                ),
            )
            progress_preview = self._run_step(
                ctx=ctx,
                step_name="step_10_update_quest_progress_preview",
                error_code="STEP_10_QUEST_PROGRESS",
                category="db",
                critical=True,
                fn=lambda: _s_quests.update_progress(
                    entry=entry,
                    user_id=ctx.user_id,
                    matched_quest_ids=matched_preview["matched_quest_ids"],
                    db=db,
                ),
            )
            quest_rewards_preview = self._run_step(
                ctx=ctx,
                step_name="step_11_compute_quest_rewards_preview",
                error_code="STEP_11_QUEST_REWARDS",
                category="config",
                critical=True,
                fn=lambda: _s_rewards.compute_quest_rewards(
                    completed_quests=progress_preview["completed_quest_payloads"],
                    variety_multiplier_bp=variety_preview.get("variety_multiplier_bp", 10000),
                    troll_bp=anomaly_result.get("troll_bp", 10000),
                    diminishing_bp=strategy_preview.get("diminishing_bp", 10000),
                ),
            )
            insight_plan = self._run_step(
                ctx=ctx,
                step_name="step_12_insight_plan",
                error_code="STEP_12_INSIGHT_PLAN",
                category="ai",
                critical=False,
                retryable=True,
                fn=lambda: _s_insights.plan(
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                    canonical_text=normalized["canonical_text"],
                    rag_hits=rag.get("hits", []),
                    detection=detection,
                    ollama_health=ollama_health,
                    ollama=self.ollama,
                    db=db,
                    cache=self.cache,
                ),
                fallback_fn=lambda _exc: {
                    "user_id": ctx.user_id,
                    "entry_id": ctx.entry_id,
                    "generated": False,
                    "persisted": False,
                    "insight_text": "",
                    "insight_category": "general",
                    "insight_confidence": 0.0,
                    "title": None,
                    "from_ollama": False,
                    "from_cache": False,
                    "citations": [],
                    "prompt_inputs": {},
                    "generation_mode": "suppressed",
                    "suppression_reason": "STEP_12_INSIGHT_PLAN",
                },
            )
            safety_result = _build_safety_result(detection)
            active_arc = ArcLifecycleService(db).get_active_arc(ctx.user_id)
            user_state = {
                "harmony_score": int(harmony_preview.get("overall_balance", 0.5) * 100),
                "anomaly_score": anomaly_result.get("anomaly_score", 0.0),
                "anomaly_contribution": anomaly_result.get("anomaly_score", 0.0),
                "tutorial_active": bool(
                    active_arc is not None and active_arc.arc_type == "tutorial"
                ),
                "regression_arc_active": bool(
                    active_arc is not None and active_arc.arc_type == "regression"
                ),
                "major_achievement": bool(progress_preview.get("completed_quest_ids")),
                "skills": detection.get("detected_skills", []),
                "overwork_stage": harmony_preview.get("overwork_stage", 0),
            }
            personality_plan = self._run_step(
                ctx=ctx,
                step_name="step_15_personality_plan",
                error_code="STEP_15_PERSONALITY_PLAN",
                category="ai",
                critical=False,
                retryable=True,
                fn=lambda: PersonalityOrchestrator(db).plan_entry_personality(
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                    entry_text=entry.content or "",
                    user_state=user_state,
                    safety_result=safety_result,
                    requested_personality=None,
                    now_utc=datetime.fromisoformat(
                        ctx.time.processing_started_at_utc.replace("Z", "+00:00")
                    ),
                    pipeline_version=ctx.versions.pipeline_version,
                ),
                fallback_fn=lambda _exc: {
                    "personality": "observer",
                    "selection_reason": "degraded_fallback",
                    "selection_factors": {},
                    "message": "[OBS] Entry recorded.",
                    "message_type": "entry_feedback",
                    "context_data": {
                        "prompt_version": "degraded",
                        "behavioral_intent_version": "degraded",
                        "selection_reason": "degraded_fallback",
                        "selection_factors": {},
                        "safety": {
                            "risk_level": safety_result.get("risk_level", "none"),
                            "force_therapist": safety_result.get("force_therapist", False),
                            "matched_rules": [],
                        },
                        "citations": [],
                        "multi_personality": {
                            "is_primary": True,
                            "impact_multiplier": 1.0,
                            "primary_personality": "observer",
                        },
                        "pipeline_version": ctx.versions.pipeline_version,
                        "generation_mode": "safe_fallback",
                        "fallback_reason": "STEP_15_PERSONALITY_PLAN",
                        "template_key": "observer.safe_fallback",
                    },
                    "generation_mode": "safe_fallback",
                    "citations": [],
                    "fallback_reason": "STEP_15_PERSONALITY_PLAN",
                    "template_key": "observer.safe_fallback",
                    "selector_version": 1,
                    "selector_seed_hash": None,
                    "logical_slot_key": "primary",
                    "thread_memories": [
                        {"role": "user", "content": entry.content or ""},
                        {
                            "role": "assistant",
                            "content": "[OBS] Entry recorded.",
                            "personality": "observer",
                            "message_type": "entry_feedback",
                        },
                    ],
                    "short_term_summary": "Entry recorded by observer.",
                    "pipeline_version": ctx.versions.pipeline_version,
                },
            )

            structured_data = self._planned_structured_data(
                canonical_text=normalized["canonical_text"],
                detection=detection,
                db=db,
                ctx=ctx,
            )
            logger.info(
                "[pipeline:trace] planning run=%s entry=%s detected_skills=%s "
                "detected_activities=%s task_type=%s matched_quests=%d completed_preview=%d "
                "reward_preview=%d confidence=%s weights=%s pattern_hits=%s",
                ctx.processing_run_id,
                ctx.entry_id,
                detection.get("detected_skills", []),
                detection.get("detected_activities", []),
                detection.get("task_type"),
                len(matched_preview.get("matched_quest_ids", [])),
                len(progress_preview.get("completed_quest_ids", [])),
                len(quest_rewards_preview.get("rewards", [])),
                structured_data.get("extraction_confidence_score", 0.0),
                structured_data.get("skills_weights_bp", {}),
                structured_data.get("pattern_hits_json", []),
            )
            if (
                not detection.get("detected_skills")
                and not detection.get("detected_activities")
            ):
                logger.warning(
                    "[pipeline:trace] planning run=%s entry=%s found no deterministic "
                    "skill/activity matches preview=%r",
                    ctx.processing_run_id,
                    ctx.entry_id,
                    (entry.content or "")[:160],
                )
            if not structured_data.get("skills_weights_bp") or float(
                structured_data.get("extraction_confidence_score", 0.0) or 0.0
            ) <= 0.0:
                logger.warning(
                    "[pipeline:trace] planning run=%s entry=%s built low-confidence "
                    "structured data confidence=%s weights=%s pattern_hits=%s",
                    ctx.processing_run_id,
                    ctx.entry_id,
                    structured_data.get("extraction_confidence_score", 0.0),
                    structured_data.get("skills_weights_bp", {}),
                    structured_data.get("pattern_hits_json", []),
                )

            db.rollback()
            return {
                "entry_content": entry.content or "",
                "normalized": normalized,
                "ollama_health": ollama_health,
                "embedding": embedding,
                "rag": rag,
                "detection": detection,
                "structured_data": structured_data,
                "safety_result": safety_result,
                "strategy_preview": strategy_preview,
                "variety_preview": variety_preview,
                "anomaly_result": anomaly_result,
                "harmony_preview": harmony_preview,
                "matched_preview": matched_preview,
                "progress_preview": progress_preview,
                "quest_rewards_preview": quest_rewards_preview,
                "insight_plan": insight_plan,
                "personality_plan": personality_plan,
            }

    def _plan_anomaly(
        self,
        db: Session,
        ctx: PipelineContext,
        entry: JournalEntry,
    ) -> dict[str, Any]:
        now = datetime.fromisoformat(
            ctx.time.processing_started_at_utc.replace("Z", "+00:00")
        )
        result = AnomalyOrchestrator(db).ensure_anomaly_score(
            user_id=ctx.user_id,
            entry_id=ctx.entry_id,
            now_utc=now,
        )
        troll_m = Decimal(str(result["troll_multiplier"])).quantize(Decimal("0.000001"))
        troll_bp = int(troll_m * Decimal("10000"))
        components = result["detection_factors"].get("components", [])
        return {
            "entry_id": entry.id,
            "anomaly_score": float(result["score"]),
            "score": float(result["score"]),
            "troll_multiplier": float(troll_m),
            "troll_bp": troll_bp,
            "detection_factors": result["detection_factors"],
            "reasons": [c.get("key", "") for c in components if c.get("key")],
            "calculated_at": result["calculated_at"],
        }

    def _serialize_quest_summary(self, quest: Any) -> dict[str, Any]:
        return {
            "quest_id": quest.id,
            "name": getattr(quest, "name", None),
            "title": getattr(quest, "name", None),
            "quest_type": quest.quest_type,
            "completion_type": quest.completion_type,
            "status": quest.status,
            "progress_value": getattr(quest, "current_progress", None),
            "required_progress": getattr(quest, "required_progress", None),
        }

    def _serialize_arc_summary(self, arc: Any) -> dict[str, Any]:
        return {
            "arc_id": arc.id,
            "arc_type": arc.arc_type,
            "status": arc.status,
            "event_name": arc.event_name,
        }

    def _execute_story_arc_stage(
        self,
        db: Session,
        ctx: PipelineContext,
        entry: JournalEntry,
    ) -> dict[str, Any]:
        user = db.query(User).filter(User.id == ctx.user_id).one_or_none()
        if user is None:
            return {
                "active_arc": None,
                "arc_updates": [],
                "notes": ["USER_NOT_FOUND"],
                "error": "USER_NOT_FOUND",
            }

        lifecycle = ArcLifecycleService(db)
        vacation_service = VacationModeService(db)
        regression_service = RegressionTriggerService(db)
        recovery_service = RecoveryDetectionService(db)

        updates: list[dict[str, Any]] = []
        notes: list[str] = []

        cached_active_arc_id = user.active_arc_id
        active_arc = lifecycle.reconcile_active_arc_cache(user.id)
        if cached_active_arc_id != (active_arc.id if active_arc else None):
            updates.append(
                {
                    "action": "cache_repaired",
                    "cached_arc_id": cached_active_arc_id,
                    "active_arc_id": active_arc.id if active_arc else None,
                }
            )

        if (
            active_arc is not None
            and active_arc.arc_type == "event"
            and active_arc.duration_days is not None
            and lifecycle.calculate_days_active(active_arc) >= float(active_arc.duration_days)
        ):
            if active_arc.event_name == "vacation_mode":
                ended_vacation, resumed_arc = vacation_service.end_vacation(user.id)
                updates.append(
                    {
                        "action": "auto_expired",
                        "arc": self._serialize_arc_summary(ended_vacation),
                    }
                )
                if resumed_arc is not None:
                    updates.append(
                        {
                            "action": "resumed",
                            "arc": self._serialize_arc_summary(resumed_arc),
                        }
                    )
                active_arc = lifecycle.reconcile_active_arc_cache(user.id)
            else:
                expired_arc = lifecycle.complete_arc(
                    arc=active_arc,
                    trigger_type="auto_expiry",
                    trigger_data={"entry_id": entry.id},
                )
                updates.append(
                    {
                        "action": "auto_expired",
                        "arc": self._serialize_arc_summary(expired_arc),
                    }
                )
                active_arc = lifecycle.reconcile_active_arc_cache(user.id)

        if active_arc is not None and active_arc.arc_type == "regression":
            prior_arc_id = active_arc.id
            redemption_arc = recovery_service.check_and_transition_to_redemption(user.id)
            active_arc = lifecycle.reconcile_active_arc_cache(user.id)
            if redemption_arc is not None:
                updates.append(
                    {
                        "action": "transitioned_to_redemption",
                        "from_arc_id": prior_arc_id,
                        "arc": self._serialize_arc_summary(redemption_arc),
                    }
                )
            elif active_arc is None or active_arc.id != prior_arc_id:
                updates.append(
                    {
                        "action": "regression_closed",
                        "from_arc_id": prior_arc_id,
                        "active_arc_id": active_arc.id if active_arc else None,
                    }
                )
        else:
            regression_arc = regression_service.check_and_trigger_regression(user.id)
            active_arc = lifecycle.reconcile_active_arc_cache(user.id)
            if regression_arc is not None:
                updates.append(
                    {
                        "action": "regression_triggered",
                        "arc": self._serialize_arc_summary(regression_arc),
                    }
                )
            elif active_arc is not None and active_arc.arc_type == "event":
                notes.append("REGRESSION_CHECK_DEFERRED_OR_SUPPRESSED")

        db.flush()
        return {
            "active_arc": (
                self._serialize_arc_summary(active_arc) if active_arc is not None else None
            ),
            "arc_updates": updates,
            "notes": notes,
        }

    def _execute_quest_matcher(
        self,
        db: Session,
        ctx: PipelineContext,
        entry: JournalEntry,
        plan: dict[str, Any],
        variety_out: dict[str, Any],
    ) -> dict[str, Any]:
        """Run QuestMatcherStep and return a JSON-serializable summary dict.

        Called from ``_apply_tx_b`` after ``step_16p_finalize_entry`` so that
        ``entry.status == 'completed'`` when the matcher runs.
        """
        user = db.query(User).filter(User.id == ctx.user_id).one_or_none()
        if user is None:
            return {
                "instant_quest_id": None,
                "streak_quest_ids": [],
                "xp_award_count": 0,
                "total_xp_awarded": 0,
                "notes": ["USER_NOT_FOUND"],
                "error": "USER_NOT_FOUND",
            }

        step = QuestMatcherStep(db)
        result = step.execute(
            user=user,
            entry=entry,
            structured_data=plan["structured_data"],
            troll_multiplier_bp=plan["anomaly_result"].get("troll_bp", 10000),
            variety_multiplier_bp=variety_out.get("variety_multiplier_bp", 10000),
            processing_run_id=ctx.processing_run_id,
        )

        # Serialize ORM objects → JSON-safe primitives for the pipeline result.
        instant = result.get("instant_quest")
        streak_quests = result.get("streak_quests", [])
        xp_awards = result.get("xp_awards", [])
        created_quests = result.get("created_quests", [])
        progressed_quests = result.get("progressed_quests", [])
        completed_quests = result.get("completed_quests", [])
        out: dict[str, Any] = {
            "instant_quest_id": instant.id if instant is not None else None,
            "streak_quest_ids": [q.id for q in streak_quests],
            "created_quests": [
                self._serialize_quest_summary(quest) for quest in created_quests
            ],
            "progressed_quests": [
                self._serialize_quest_summary(quest) for quest in progressed_quests
            ],
            "completed_quests": [
                self._serialize_quest_summary(quest) for quest in completed_quests
            ],
            "xp_awards": [
                {
                    "id": award.id,
                    "quest_id": award.quest_id,
                    "skill_id": award.skill_id,
                    "theme_id": award.theme_id,
                    "distribution_type": award.distribution_type,
                    "amount": award.amount,
                    "xp_reason": award.xp_reason,
                }
                for award in xp_awards
            ],
            "xp_award_count": len(xp_awards),
            "total_xp_awarded": result.get("total_xp_awarded", 0),
            "notes": result.get("notes", []),
            "progression": result.get("progression", {}),
        }
        if "error" in result:
            out["error"] = result["error"]
        logger.info(
            "[pipeline:quest_matcher] serialized entry=%s instant=%s created=%d "
            "progressed=%d completed=%d xp_award_count=%d total_xp=%d progression=%s "
            "notes=%s",
            entry.id,
            out["instant_quest_id"],
            len(out["created_quests"]),
            len(out["progressed_quests"]),
            len(out["completed_quests"]),
            out["xp_award_count"],
            out["total_xp_awarded"],
            out["progression"],
            out["notes"],
        )
        return out

    @staticmethod
    def _system_report_section_title(section_key: str) -> str:
        titles = {
            "signals": "Signals",
            "xp": "XP",
            "quests": "Quests",
            "strategy": "Strategy",
            "anomaly_variety": "Anomaly / Variety",
            "insight": "Insight",
            "personality_reply": "Personality Reply",
        }
        return titles.get(section_key, section_key.replace("_", " ").title())

    def _compose_system_report_message(
        self,
        *,
        ctx: "PipelineContext",
        approx_ms: int,
        completion_status: str,
        missing_sections: list[str],
        section_statuses: dict[str, dict[str, Any]],
    ) -> str:
        lines = [
            "SYSTEM REPORT CHECKLIST",
            f"Date: {ctx.time.local_event_date}",
            f"Processing: ~{approx_ms} ms",
            f"Completion: {completion_status}",
        ]
        if missing_sections:
            lines.append(
                "Missing sections: "
                + ", ".join(self._system_report_section_title(key) for key in missing_sections)
            )
        else:
            lines.append("Missing sections: none")

        ordered_sections = [
            "signals",
            "xp",
            "quests",
            "strategy",
            "anomaly_variety",
            "insight",
            "personality_reply",
        ]
        for section_key in ordered_sections:
            section = dict(section_statuses.get(section_key, {}) or {})
            status = str(section.get("status", "missing"))
            details = [
                str(detail)
                for detail in list(section.get("details", []) or [])
                if str(detail).strip()
            ]
            lines.append("")
            lines.append(f"[{self._system_report_section_title(section_key)}] {status}")
            if details:
                lines.extend(f"- {detail}" for detail in details)
            else:
                lines.append("- no details available")
        return "\n".join(lines)

    def _resolve_skill_labels_for_report(
        self,
        *,
        user_id: str,
        skills: list[str],
        db: Session | None,
    ) -> list[str]:
        normalized: list[str] = []
        seen_inputs: set[str] = set()
        for raw in skills:
            value = str(raw or "").strip()
            if not value:
                continue
            if value in seen_inputs:
                continue
            seen_inputs.add(value)
            normalized.append(value)

        if not normalized or db is None:
            return normalized

        user_skill_rows = (
            db.query(Skill)
            .filter(Skill.user_id == user_id, Skill.id.in_(normalized))
            .all()
        )
        user_skill_names = {str(row.id): str(row.name) for row in user_skill_rows}

        global_source_rows = (
            db.query(GlobalSkill)
            .filter(GlobalSkill.source_skill_id.in_(normalized))
            .all()
        )
        global_source_names = {
            str(row.source_skill_id): str(row.canonical_name)
            for row in global_source_rows
            if row.source_skill_id
        }

        global_id_rows = db.query(GlobalSkill).filter(GlobalSkill.id.in_(normalized)).all()
        global_id_names = {str(row.id): str(row.canonical_name) for row in global_id_rows}

        resolved: list[str] = []
        seen_resolved: set[str] = set()
        for value in normalized:
            label = (
                user_skill_names.get(value)
                or global_source_names.get(value)
                or global_id_names.get(value)
                or value
            )
            if label in seen_resolved:
                continue
            seen_resolved.add(label)
            resolved.append(label)
        return resolved

    def _resolve_quest_labels_for_report(
        self,
        *,
        quest_ids: list[str],
        db: Session | None,
    ) -> dict[str, str]:
        normalized_ids = sorted({str(qid).strip() for qid in quest_ids if str(qid).strip()})
        if not normalized_ids or db is None:
            return {}
        rows = db.query(Quest).filter(Quest.id.in_(normalized_ids)).all()
        return {
            str(row.id): str(row.name)
            for row in rows
            if str(getattr(row, "name", "") or "").strip()
        }

    def _format_xp_award_for_report(
        self,
        *,
        award: dict[str, Any],
        quest_names_by_id: dict[str, str],
        skill_names_by_id: dict[str, str],
        theme_names_by_id: dict[str, str],
    ) -> str:
        amount = int(award.get("amount", award.get("xp_awarded", 0)) or 0)

        skill_name = award.get("skill_name")
        if not skill_name and award.get("skill_id"):
            skill_name = skill_names_by_id.get(str(award.get("skill_id")))

        theme_name = award.get("theme_name")
        if not theme_name and award.get("theme_id"):
            theme_name = theme_names_by_id.get(str(award.get("theme_id")))

        destination_label = str(
            skill_name
            or theme_name
            or award.get("skill_id")
            or award.get("theme_id")
            or "unknown_destination"
        )

        quest_id = str(award.get("quest_id") or "").strip()
        quest_label = (
            quest_names_by_id.get(quest_id)
            if quest_id
            else None
        ) or (quest_id if quest_id else None)

        reason = str(award.get("xp_reason") or award.get("distribution_type") or "unspecified")

        detail_parts: list[str] = [f"target: {destination_label}"]
        if quest_label:
            detail_parts.append(f"quest: {quest_label}")
        detail_parts.append(f"reason: {reason}")
        return f"{' | '.join(detail_parts)}: +{amount} XP"

    def _fallback_system_report_payload(
        self,
        *,
        ctx: "PipelineContext",
        run_started: datetime,
        personality_out: dict[str, Any],
        error: Exception,
    ) -> dict[str, Any]:
        approx_ms = max(0, int((_now_utc() - run_started).total_seconds() * 1000))
        personality_present = bool(
            str(personality_out.get("message", "")).strip()
            or str(personality_out.get("personality", "")).strip()
        )
        section_statuses: dict[str, dict[str, Any]] = {
            "signals": {
                "status": "missing",
                "details": ["report builder fallback triggered before signal summary completed"],
            },
            "xp": {
                "status": "missing",
                "details": ["report builder fallback triggered before XP summary completed"],
            },
            "quests": {
                "status": "missing",
                "details": ["report builder fallback triggered before quest summary completed"],
            },
            "strategy": {
                "status": "missing",
                "details": ["report builder fallback triggered before strategy summary completed"],
            },
            "anomaly_variety": {
                "status": "missing",
                "details": ["report builder fallback triggered before anomaly summary completed"],
            },
            "insight": {
                "status": "missing",
                "details": ["report builder fallback triggered before insight summary completed"],
            },
            "personality_reply": {
                "status": "present" if personality_present else "missing",
                "details": (
                    [
                        f"personality: {personality_out.get('personality', 'unknown')}",
                        f"generation_mode: {personality_out.get('generation_mode', 'unknown')}",
                        "system report used fallback output",
                    ]
                    if personality_present
                    else ["no personality reply details were available for the fallback report"]
                ),
            },
        }
        missing_sections = [
            key
            for key, value in section_statuses.items()
            if str(value.get("status", "missing")) == "missing"
        ]
        completion_status = "partial"
        context_data = {
            "report_kind": "daily",
            "completion_status": completion_status,
            "missing_sections": missing_sections,
            "section_statuses": section_statuses,
            "approx_processing_ms": approx_ms,
            "pipeline_version": ctx.versions.pipeline_version,
            "error_code": f"STEP_15B_REPORT_FAILED:{type(error).__name__}",
        }
        message_text = self._compose_system_report_message(
            ctx=ctx,
            approx_ms=approx_ms,
            completion_status=completion_status,
            missing_sections=missing_sections,
            section_statuses=section_statuses,
        )
        return {
            "personality": "system",
            "message_type": "report_summary",
            "message_text": message_text,
            "logical_slot_key": "system_report",
            "selector_version": 1,
            "context_data": context_data,
            "approx_processing_ms": approx_ms,
            "fallback_used": True,
        }

    def _build_system_report_payload(
        self,
        *,
        ctx: "PipelineContext",
        detection: dict[str, Any],
        structured_data: dict[str, Any],
        skill_awards: dict[str, Any],
        theme_awards: dict[str, Any],
        anomaly_result: dict[str, Any],
        variety_out: dict[str, Any],
        strategy_out: dict[str, Any],
        quest_matcher_out: dict[str, Any] | None,
        insight_out: dict[str, Any],
        personality_out: dict[str, Any],
        run_started: datetime,
        db: Session | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Build a deterministic system pipeline report payload."""

        from src.db.models.personality import PersonalityMessage

        approx_ms = max(0, int((_now_utc() - run_started).total_seconds() * 1000))

        skills = list(
            structured_data.get("resolved_skill_names")
            or detection.get("detected_skills", [])
            or []
        )
        skills = self._resolve_skill_labels_for_report(
            user_id=ctx.user_id,
            skills=skills,
            db=db,
        )
        emotions = list(
            structured_data.get("dominant_emotions")
            or detection.get("dominant_emotions", [])
            or []
        )
        energy = structured_data.get("energy_level", detection.get("energy_level"))

        all_awards = list(
            list(skill_awards.get("skill_awards", []))
            + list(theme_awards.get("theme_awards", []))
            + list((quest_matcher_out or {}).get("xp_awards", []))
        )

        quest_ids_for_lookup = [
            str(quest.get("quest_id") or "")
            for quest in (
                list((quest_matcher_out or {}).get("created_quests", []) or [])
                + list((quest_matcher_out or {}).get("completed_quests", []) or [])
                + list((quest_matcher_out or {}).get("progressed_quests", []) or [])
            )
        ] + [str(award.get("quest_id") or "") for award in all_awards]
        quest_names_by_id = self._resolve_quest_labels_for_report(
            quest_ids=quest_ids_for_lookup,
            db=db,
        )

        skill_ids_for_lookup = sorted(
            {
                str(award.get("skill_id"))
                for award in all_awards
                if award.get("skill_id")
            }
        )
        theme_ids_for_lookup = sorted(
            {
                str(award.get("theme_id"))
                for award in all_awards
                if award.get("theme_id")
            }
        )
        skill_names_by_id = {}
        theme_names_by_id = {}
        if db is not None and skill_ids_for_lookup:
            skill_rows = db.query(Skill).filter(Skill.id.in_(skill_ids_for_lookup)).all()
            skill_names_by_id = {str(row.id): str(row.name) for row in skill_rows}
        if db is not None and theme_ids_for_lookup:
            theme_rows = db.query(Theme).filter(Theme.id.in_(theme_ids_for_lookup)).all()
            theme_names_by_id = {str(row.id): str(row.name) for row in theme_rows}

        total_xp = sum(
            int(award.get("amount", award.get("xp_awarded", 0)) or 0)
            for award in all_awards
        )
        award_summaries = []
        for award in all_awards:
            award_summaries.append(
                self._format_xp_award_for_report(
                    award=award,
                    quest_names_by_id=quest_names_by_id,
                    skill_names_by_id=skill_names_by_id,
                    theme_names_by_id=theme_names_by_id,
                )
            )

        created_quests = list((quest_matcher_out or {}).get("created_quests", []) or [])
        completed_quests = list(
            (quest_matcher_out or {}).get("completed_quests", []) or []
        )
        progressed_quests = list(
            (quest_matcher_out or {}).get("progressed_quests", []) or []
        )
        quest_details = []
        if created_quests:
            quest_details.append(
                "created: "
                + ", ".join(
                    str(
                        quest.get("title")
                        or quest.get("name")
                        or quest_names_by_id.get(str(quest.get("quest_id") or ""))
                        or quest.get("quest_id", "?")
                    )
                    for quest in created_quests[:3]
                )
            )
        if completed_quests:
            quest_details.append(
                "completed: "
                + ", ".join(
                    str(
                        quest.get("title")
                        or quest.get("name")
                        or quest_names_by_id.get(str(quest.get("quest_id") or ""))
                        or quest.get("quest_id", "?")
                    )
                    for quest in completed_quests[:3]
                )
            )
        if progressed_quests:
            progress_parts = []
            for quest in progressed_quests[:3]:
                label = str(
                    quest.get("title")
                    or quest.get("name")
                    or quest_names_by_id.get(str(quest.get("quest_id") or ""))
                    or quest.get("quest_id", "?")
                )
                progress_value = quest.get("progress_value")
                required_progress = quest.get("required_progress")
                if progress_value is not None and required_progress is not None:
                    label = f"{label} ({progress_value}/{required_progress})"
                progress_parts.append(label)
            quest_details.append("progressed: " + ", ".join(progress_parts))

        detected_strategies = list(strategy_out.get("detected_strategies", []) or [])
        anomaly_score = anomaly_result.get("score")
        troll_multiplier = anomaly_result.get("troll_multiplier")
        if troll_multiplier is None:
            troll_multiplier = float(anomaly_result.get("troll_bp", 10000)) / 10000
        variety_bonus = variety_out.get("variety_bonus_pct", 0.0)
        variety_multiplier_bp = variety_out.get("variety_multiplier_bp")
        variety_multiplier = (
            float(variety_multiplier_bp) / 10000
            if variety_multiplier_bp is not None
            else None
        )

        insight_text = str(insight_out.get("insight_text", "") or "").strip()
        insight_title = str(insight_out.get("title", "") or "").strip()
        personality_message = str(personality_out.get("message", "") or "").strip()
        personality_name = str(personality_out.get("personality", "") or "").strip()

        section_statuses: dict[str, dict[str, Any]] = {
            "signals": {
                "status": "present" if (skills or emotions or energy is not None) else "missing",
                "details": [
                    "skills: " + ", ".join(skills) if skills else "skills: missing",
                    "emotions: " + ", ".join(emotions) if emotions else "emotions: missing",
                    f"energy: {energy}" if energy is not None else "energy: missing",
                ],
            },
            "xp": {
                "status": "present" if (all_awards or total_xp > 0) else "missing",
                "details": [f"total: +{total_xp} XP"]
                + (award_summaries or ["no XP awards were produced"]),
            },
            "quests": {
                "status": "present"
                if (created_quests or completed_quests or progressed_quests)
                else "missing",
                "details": quest_details or ["no quest changes were recorded"],
            },
            "strategy": {
                "status": "present" if detected_strategies else "missing",
                "details": (
                    ["detected: " + ", ".join(detected_strategies)]
                    if detected_strategies
                    else ["no strategy detected"]
                ),
            },
            "anomaly_variety": {
                "status": "present" if (anomaly_result or variety_out) else "missing",
                "details": [
                    (
                        f"anomaly_score: {float(anomaly_score):.2f}"
                        if anomaly_score is not None
                        else "anomaly_score: missing"
                    ),
                    f"troll_multiplier: {float(troll_multiplier):.2f}x",
                    f"variety_bonus: {float(variety_bonus):.2f}%",
                    (
                        f"variety_multiplier: {float(variety_multiplier):.2f}x"
                        if variety_multiplier is not None
                        else "variety_multiplier: missing"
                    ),
                ],
            },
            "insight": {
                "status": "present" if (insight_text or insight_out.get("insight_id")) else "missing",
                "details": (
                    [
                        "title: " + insight_title if insight_title else "title: missing",
                        "summary: " + insight_text if insight_text else "summary: missing",
                        f"generation_mode: {insight_out.get('generation_mode', 'unknown')}",
                    ]
                    if (insight_text or insight_out.get("insight_id"))
                    else [
                        f"generation_mode: {insight_out.get('generation_mode', 'suppressed')}",
                        (
                            "reason: " + str(insight_out.get("suppression_reason"))
                            if insight_out.get("suppression_reason")
                            else "no insight generated"
                        ),
                    ]
                ),
            },
            "personality_reply": {
                "status": "present" if (personality_message or personality_name) else "missing",
                "details": (
                    [
                        (
                            f"personality: {personality_name}"
                            if personality_name
                            else "personality: missing"
                        ),
                        f"generation_mode: {personality_out.get('generation_mode', 'unknown')}",
                        f"inserted: {'yes' if personality_out.get('inserted') else 'no'}",
                        (
                            "preview: "
                            + (
                                personality_message[:117] + "..."
                                if len(personality_message) > 120
                                else personality_message
                            )
                            if personality_message
                            else "preview: missing"
                        ),
                    ]
                    if (personality_message or personality_name)
                    else ["no personality reply was available when the report was built"]
                ),
            },
        }

        missing_sections = [
            key
            for key, value in section_statuses.items()
            if str(value.get("status", "missing")) == "missing"
        ]
        completion_status = "complete" if not missing_sections else "partial"
        context_data = {
            "report_kind": "daily",
            "completion_status": completion_status,
            "missing_sections": missing_sections,
            "section_statuses": section_statuses,
            "approx_processing_ms": approx_ms,
            "pipeline_version": ctx.versions.pipeline_version,
        }
        message_text = self._compose_system_report_message(
            ctx=ctx,
            approx_ms=approx_ms,
            completion_status=completion_status,
            missing_sections=missing_sections,
            section_statuses=section_statuses,
        )

        return {
            "personality": "system",
            "message_type": "report_summary",
            "message_text": message_text,
            "logical_slot_key": "system_report",
            "selector_version": 1,
            "context_data": context_data,
            "approx_processing_ms": approx_ms,
            "fallback_used": False,
        }

        approx_ms = int((_now_utc() - run_started).total_seconds() * 1000)

        lines: list[str] = [
            f"SYSTEM REPORT — {ctx.time.local_event_date}",
            f"Processing: ~{approx_ms} ms",
        ]

        skills = detection.get("detected_skills", [])
        if skills:
            lines.append(f"\n--- SKILLS ---\n  {', '.join(str(s) for s in skills)}")

        emotions = detection.get("dominant_emotions", [])
        energy = detection.get("energy_level")
        if emotions or energy is not None:
            parts: list[str] = []
            if emotions:
                parts.append(f"emotions: {', '.join(str(e) for e in emotions)}")
            if energy is not None:
                parts.append(f"energy: {energy}")
            lines.append(f"\n--- SIGNALS ---\n  {' | '.join(parts)}")

        all_awards = (
            list(skill_awards.get("skill_awards", []))
            + list(theme_awards.get("theme_awards", []))
            + list((quest_matcher_out or {}).get("xp_awards", []))
        )
        if all_awards:
            lines.append("\n--- XP GAINS ---")
            for award in all_awards:
                name = award.get("skill_name") or award.get("theme_name", "?")
                amt = award.get("amount", award.get("xp_awarded", 0))
                lines.append(f"  {name}: +{amt} XP")

        troll_bp = anomaly_result.get("troll_bp", 10000)
        variety_bp = variety_out.get("variety_multiplier_bp", 10000)
        if any(x != 10000 for x in [troll_bp, variety_bp]):
            lines.append("\n--- MULTIPLIERS ---")
            if troll_bp != 10000:
                lines.append(f"  Troll:   {troll_bp / 10000:.2f}x")
            if variety_bp != 10000:
                lines.append(f"  Variety: {variety_bp / 10000:.2f}x")

        completed = list((quest_matcher_out or {}).get("completed_quests", []))
        progressed = list((quest_matcher_out or {}).get("progressed_quests", []))
        if completed or progressed:
            lines.append("\n--- QUESTS ---")
            for q in completed:
                lines.append(f"  COMPLETED:  {q.get('title', q.get('quest_id', '?'))}")
            for q in progressed:
                lines.append(f"  Progressed: {q.get('title', q.get('quest_id', '?'))}")

        detected_strategies = strategy_out.get("detected_strategies", [])
        if detected_strategies:
            lines.append(f"\n--- STRATEGY ---\n  {', '.join(str(s) for s in detected_strategies)}")

        message_text = "\n".join(lines)
        context_data = json.dumps({
            "pipeline_version": ctx.versions.pipeline_version,
            "approx_processing_ms": approx_ms,
            "skills": list(skills),
            "troll_bp": troll_bp,
            "variety_bp": variety_bp,
        })

        row = PersonalityMessage(
            id=str(uuid.uuid4()),
            user_id=ctx.user_id,
            entry_id=ctx.entry_id,
            personality="system",
            message_type="report_summary",
            message_text=message_text,
            selector_version=1,
            selector_seed_hash=None,
            logical_slot_key="system_report",
            context_data=context_data,
            quest_id=None,
            created_at=now,
        )
        db.add(row)

        return {
            "personality": "system",
            "message_type": "report_summary",
            "message_text": message_text,
            "logical_slot_key": "system_report",
            "approx_processing_ms": approx_ms,
        }

    def _persist_system_report_message(
        self,
        *,
        db: Session,
        ctx: "PipelineContext",
        report_result: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        stored = MessagePersistenceService(db).store_message(
            user_id=ctx.user_id,
            entry_id=ctx.entry_id,
            personality="system",
            message_type="report_summary",
            message_text=str(
                report_result.get("message_text") or "[SYSTEM] No report available."
            ),
            selector_version=int(report_result.get("selector_version", 1) or 1),
            selector_seed_hash=None,
            logical_slot_key=str(
                report_result.get("logical_slot_key") or "system_report"
            ),
            context_data=dict(report_result.get("context_data", {}) or {}),
            quest_id=None,
            now_utc=now,
        )
        message = stored["message"]
        return {
            "message_id": str(message.id),
            "inserted": bool(stored["inserted"]),
        }

    def _build_xp_lineage(
        self,
        *,
        db: Session,
        structured_data: dict[str, Any],
        quest_matcher_out: dict[str, Any],
    ) -> dict[str, Any]:
        from src.core.skill_unlocks import SkillUnlockService

        resolver = SkillUnlockService(db)
        hierarchy = resolver.hierarchy
        source_skill_weights_bp = dict(
            structured_data.get("source_skills_weights_bp", {}) or {}
        )
        final_distributions = dict(
            (quest_matcher_out.get("progression", {}) or {}).get("xp_distributions", {})
            or {}
        )

        def _path_to_target(source_skill_id: str, target_skill_id: str) -> list[str]:
            if source_skill_id == target_skill_id:
                return [source_skill_id]
            frontier: list[tuple[str, list[str]]] = [(source_skill_id, [source_skill_id])]
            seen = {source_skill_id}
            while frontier:
                current, path = frontier.pop(0)
                parents = hierarchy.get(current, {}).get("parent_skill_ids", [])
                for parent_id in parents:
                    if parent_id in seen:
                        continue
                    next_path = path + [parent_id]
                    if parent_id == target_skill_id:
                        return next_path
                    seen.add(parent_id)
                    frontier.append((parent_id, next_path))
            return []

        redirect_paths: list[dict[str, Any]] = []
        for source_skill_id in source_skill_weights_bp:
            for target_skill_id, xp_amount in final_distributions.items():
                path = _path_to_target(source_skill_id, target_skill_id)
                if not path:
                    continue
                redirect_paths.append(
                    {
                        "source_skill_id": source_skill_id,
                        "target_skill_id": target_skill_id,
                        "path": path,
                        "xp_amount": xp_amount,
                        "reason": (
                            "xp redirected to an XP-eligible ancestor under hierarchy rules"
                            if source_skill_id != target_skill_id
                            else "xp stayed on the directly resolved source skill"
                        ),
                    }
                )

        return {
            "resolved_skill_names": list(structured_data.get("resolved_skill_names", [])),
            "source_skill_weights_bp": source_skill_weights_bp,
            "user_skill_weights_bp": dict(structured_data.get("skills_weights_bp", {}) or {}),
            "pattern_hits_json": list(structured_data.get("pattern_hits_json", [])),
            "final_xp_distributions": final_distributions,
            "redirect_paths": redirect_paths,
            "redirected_to_ancestor": any(
                item["source_skill_id"] != item["target_skill_id"]
                for item in redirect_paths
            ),
            "final_target_skill_ids": sorted(final_distributions),
        }

    def _apply_tx_b(
        self,
        ctx: PipelineContext,
        plan: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        with self._new_session() as db, self._use_db(db), forbid_network_calls():
            entry = self._get_entry(user_id=ctx.user_id, entry_id=ctx.entry_id)
            job = self._get_job(job_id=ctx.job_id, user_id=ctx.user_id)
            if entry is None or job is None:
                raise PipelineStepError(
                    "step_16_tx_b_finalize",
                    "PIPELINE_INVARIANT_VIOLATION",
                    "entry or processing job disappeared before Tx B finalization",
                )

            run_started = datetime.fromisoformat(
                ctx.time.processing_started_at_utc.replace("Z", "+00:00")
            )

            structured = self._run_step(
                ctx=ctx,
                step_name="step_16a_persist_structured",
                error_code="STEP_16A_STRUCTURED_PERSIST",
                category="db",
                critical=True,
                fn=lambda: _s_structured.run(
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                    canonical_text=plan["normalized"]["canonical_text"],
                    detection=plan["detection"],
                    resolved_skill_names=plan["structured_data"].get(
                        "resolved_skill_names", []
                    ),
                    db=db,
                ),
            )
            anomaly_persisted = self._run_step(
                ctx=ctx,
                step_name="step_16b_persist_anomaly",
                error_code="STEP_16B_ANOMALY_PERSIST",
                category="db",
                critical=True,
                fn=lambda: AnomalyOrchestrator(db).persist_planned_result(
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                    planned_result={
                        "score": plan["anomaly_result"]["score"],
                        "troll_multiplier": plan["anomaly_result"]["troll_multiplier"],
                        "detection_factors": plan["anomaly_result"]["detection_factors"],
                        "calculated_at": plan["anomaly_result"]["calculated_at"],
                    },
                ),
            )
            strategy_out = self._run_step(
                ctx=ctx,
                step_name="step_16c_strategy_persist",
                error_code="STEP_16C_STRATEGY_PERSIST",
                category="db",
                critical=False,
                retryable=True,
                fn=lambda: _s_strategy.run(
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                    canonical_text=plan["normalized"]["canonical_text"],
                    detection=plan["detection"],
                    anomaly_score=plan["anomaly_result"].get("anomaly_score", 0.0),
                    db=db,
                ),
                fallback_fn=lambda _exc: {
                    "detected_strategies": [],
                    "strategy_scores": {},
                    "diminishing_multiplier": 1.0,
                    "diminishing_bp": 10000,
                },
            )
            variety_out = self._run_step(
                ctx=ctx,
                step_name="step_16d_variety_persist",
                error_code="STEP_16D_VARIETY_PERSIST",
                category="db",
                critical=False,
                retryable=True,
                fn=lambda: _s_variety.run(user_id=ctx.user_id, db=db),
                fallback_fn=lambda _exc: {
                    "variety_score": 0.0,
                    "variety_bonus_pct": 0.0,
                    "variety_multiplier_bp": 10000,
                    "strategy_counts": {},
                    "window_days": 30,
                },
            )
            harmony_out = self._run_step(
                ctx=ctx,
                step_name="step_16e_harmony_persist",
                error_code="STEP_16E_HARMONY_PERSIST",
                category="db",
                critical=False,
                retryable=True,
                fn=lambda: _harmony_step(
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                    entry=entry,
                    db=db,
                ),
                fallback_fn=lambda _exc: {
                    "dimensions_addressed": [],
                    "overall_balance": 0.5,
                    "overwork_stage": 0,
                },
            )
            matched = self._run_step(
                ctx=ctx,
                step_name="step_16f_match_quests",
                error_code="STEP_16F_QUEST_MATCH",
                category="db",
                critical=True,
                fn=lambda: _s_quests.match(
                    entry=entry,
                    user_id=ctx.user_id,
                    detected_skills=plan["detection"]["detected_skills"],
                    detected_activities=plan["detection"]["detected_activities"],
                    db=db,
                ),
            )
            progress = self._run_step(
                ctx=ctx,
                step_name="step_16g_progress_quests",
                error_code="STEP_16G_QUEST_PROGRESS",
                category="db",
                critical=True,
                fn=lambda: _s_quests.update_progress(
                    entry=entry,
                    user_id=ctx.user_id,
                    matched_quest_ids=matched["matched_quest_ids"],
                    db=db,
                ),
            )
            quest_rewards = self._run_step(
                ctx=ctx,
                step_name="step_16h_compute_rewards",
                error_code="STEP_16H_REWARD_COMPUTE",
                category="config",
                critical=True,
                fn=lambda: _s_rewards.compute_quest_rewards(
                    completed_quests=progress["completed_quest_payloads"],
                    variety_multiplier_bp=variety_out.get("variety_multiplier_bp", 10000),
                    troll_bp=plan["anomaly_result"].get("troll_bp", 10000),
                    diminishing_bp=strategy_out.get("diminishing_bp", 10000),
                ),
            )
            skill_awards = self._run_step(
                ctx=ctx,
                step_name="step_16i_persist_skill_awards",
                error_code="STEP_16I_SKILL_AWARDS",
                category="db",
                critical=True,
                fn=lambda: _s_rewards.persist_skill_awards(
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                    processing_run_id=ctx.processing_run_id,
                    rewards=quest_rewards["rewards"],
                    db=db,
                    pipeline_version=ctx.versions.pipeline_version,
                    ruleset_version=ctx.versions.ruleset_version,
                ),
            )
            theme_awards = self._run_step(
                ctx=ctx,
                step_name="step_16j_persist_theme_awards",
                error_code="STEP_16J_THEME_AWARDS",
                category="db",
                critical=True,
                fn=lambda: _s_rewards.persist_theme_awards(
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                    processing_run_id=ctx.processing_run_id,
                    skill_awards=skill_awards["skill_awards"],
                    db=db,
                    pipeline_version=ctx.versions.pipeline_version,
                    ruleset_version=ctx.versions.ruleset_version,
                ),
            )
            progression_out = self._run_step(
                ctx=ctx,
                step_name="step_16k_progression_update",
                error_code="STEP_16K_PROGRESSION",
                category="db",
                critical=True,
                fn=lambda: _s_progression.update_counters(
                    skill_awards=skill_awards["skill_awards"],
                    theme_awards=theme_awards["theme_awards"],
                    db=db,
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                ),
            )
            insight_out = self._run_step(
                ctx=ctx,
                step_name="step_16l_persist_insight",
                error_code="STEP_16L_INSIGHT_PERSIST",
                category="db",
                critical=False,
                retryable=True,
                fn=lambda: _s_insights.persist_planned(plan=plan["insight_plan"], db=db),
                fallback_fn=lambda _exc: {
                    "insight_id": None,
                    "generated": False,
                    "persisted": False,
                    "insight_text": "",
                    "insight_category": "general",
                    "insight_confidence": 0.0,
                    "title": plan["insight_plan"].get("title"),
                    "from_ollama": False,
                    "from_cache": False,
                    "citations": [],
                    "prompt_inputs": dict(plan["insight_plan"].get("prompt_inputs", {}) or {}),
                    "generation_mode": "suppressed",
                    "suppression_reason": "STEP_16L_INSIGHT_PERSIST",
                },
            )
            self._run_step(
                ctx=ctx,
                step_name="step_16m_reset_staleness",
                error_code="STEP_16M_STALENESS",
                category="db",
                critical=False,
                retryable=True,
                fn=lambda: _staleness_reset_step(
                    user_id=ctx.user_id,
                    skill_awards=skill_awards["skill_awards"],
                    now_utc=run_started,
                    db=db,
                ),
                fallback_fn=lambda _exc: {"skills_reset": 0},
            )
            personality_out = self._run_step(
                ctx=ctx,
                step_name="step_16n_persist_personality",
                error_code="STEP_16N_PERSONALITY_PERSIST",
                category="db",
                critical=False,
                retryable=True,
                fn=lambda: PersonalityOrchestrator(db).apply_entry_personality_plan(
                    user_id=ctx.user_id,
                    entry_id=ctx.entry_id,
                    entry_text=plan["entry_content"],
                    plan=plan["personality_plan"],
                    now_utc=run_started,
                ),
                fallback_fn=lambda _exc: {
                    "personality": "observer",
                    "selection_reason": "degraded_fallback",
                    "message": "[OBS] Entry recorded.",
                    "message_id": None,
                    "context_data": plan["personality_plan"].get("context_data", {}),
                    "generation_mode": "safe_fallback",
                    "citations": [],
                    "fallback_reason": "STEP_16N_PERSONALITY_PERSIST",
                    "template_key": "observer.safe_fallback",
                    "inserted": False,
                },
            )
            summary = self._run_step(
                ctx=ctx,
                step_name="step_16o_build_summary",
                error_code="STEP_16O_SUMMARY",
                category="config",
                critical=True,
                fn=lambda: _s_summary.build(
                    rag_hits=plan["rag"].get("hits", []),
                    detection=plan["detection"],
                    progress=progress,
                    skill_awards=skill_awards,
                    theme_awards=theme_awards,
                    variety=variety_out,
                    anomaly=plan["anomaly_result"],
                    insight=insight_out,
                    detected_strategies=strategy_out.get("detected_strategies", []),
                    strategy=strategy_out,
                ),
            )
            finalize = self._run_step(
                ctx=ctx,
                step_name="step_16p_finalize_entry",
                error_code="STEP_16P_ENTRY_FINALIZE",
                category="db",
                critical=True,
                fn=lambda: _s_entry.mark_completed(
                    entry=entry,
                    run_started=run_started,
                    db=db,
                ),
            )
            story_arc_out = self._run_step(
                ctx=ctx,
                step_name="step_16q_story_arc_stage",
                error_code="STEP_16Q_STORY_ARCS",
                category="db",
                critical=False,
                retryable=False,
                fn=lambda: self._execute_story_arc_stage(
                    db=db,
                    ctx=ctx,
                    entry=entry,
                ),
                fallback_fn=lambda exc: {
                    "active_arc": None,
                    "arc_updates": [],
                    "notes": [str(exc)],
                    "error": str(exc),
                },
            )
            # Step 16r — Quest Matcher v2 (Section 10).
            # Runs AFTER step_16p so entry.status == "completed", which is
            # required by QuestMatcherService.match_quests_for_entry.
            quest_matcher_out = self._run_step(
                ctx=ctx,
                step_name="step_16r_quest_matcher",
                error_code="STEP_16R_QUEST_MATCHER",
                category="db",
                critical=False,
                retryable=False,
                fn=lambda: self._execute_quest_matcher(
                    db=db,
                    ctx=ctx,
                    entry=entry,
                    plan=plan,
                    variety_out=variety_out,
                ),
                fallback_fn=lambda exc: {
                    "instant_quest_id": None,
                    "streak_quest_ids": [],
                    "xp_award_count": 0,
                    "total_xp_awarded": 0,
                    "notes": [],
                    "error": str(exc),
                },
            )
            quest_matcher_out["xp_lineage"] = self._build_xp_lineage(
                db=db,
                structured_data=plan["structured_data"],
                quest_matcher_out=quest_matcher_out,
            )
            report_result = self._run_step(
                ctx=ctx,
                step_name="step_15b_system_report",
                error_code="STEP_15B_REPORT_FAILED",
                category="db",
                critical=False,
                retryable=False,
                fn=lambda: self._build_system_report_payload(
                    ctx=ctx,
                    detection=plan["detection"],
                    structured_data=plan["structured_data"],
                    skill_awards=skill_awards,
                    theme_awards=theme_awards,
                    anomaly_result=plan["anomaly_result"],
                    variety_out=variety_out,
                    strategy_out=strategy_out,
                    quest_matcher_out=quest_matcher_out,
                    insight_out=insight_out,
                    personality_out=personality_out,
                    run_started=run_started,
                    db=db,
                ),
                fallback_fn=lambda exc: self._fallback_system_report_payload(
                    ctx=ctx,
                    run_started=run_started,
                    personality_out=personality_out,
                    error=exc,
                ),
            )
            report_persist_result = self._run_step(
                ctx=ctx,
                step_name="step_16s_persist_system_report",
                error_code="STEP_16S_SYSTEM_REPORT_PERSIST",
                category="db",
                critical=False,
                retryable=True,
                fn=lambda: self._persist_system_report_message(
                    db=db,
                    ctx=ctx,
                    report_result=report_result or {},
                    now=_now_utc(),
                ),
                fallback_fn=lambda exc: {
                    "message_id": None,
                    "inserted": False,
                    "error": str(exc),
                },
            )
            report_result = {**(report_result or {}), **(report_persist_result or {})}
            persisted_personality_messages = serialize_personality_messages(
                db.query(PersonalityMessage)
                .filter(
                    PersonalityMessage.user_id == ctx.user_id,
                    PersonalityMessage.entry_id == ctx.entry_id,
                )
                .order_by(
                    PersonalityMessage.created_at.asc(),
                    PersonalityMessage.logical_slot_key.asc(),
                    PersonalityMessage.id.asc(),
                )
                .all()
            )

            processing_completed_at = _iso8601z(entry.processed_at or _now_utc())
            ctx.time.processing_completed_at_utc = processing_completed_at
            result = self._build_success_result(
                ctx=ctx,
                structured=structured,
                plan=plan,
                progress=progress,
                skill_awards=skill_awards,
                theme_awards=theme_awards,
                progression_out=progression_out,
                harmony_out=harmony_out,
                strategy_out=strategy_out,
                variety_out=variety_out,
                insight_out=insight_out,
                anomaly_out=anomaly_persisted,
                personality_out=personality_out,
                persisted_personality_messages=persisted_personality_messages,
                summary=summary,
                finalize=finalize,
                story_arc_out=story_arc_out,
                quest_matcher_out=quest_matcher_out,
                report_result=report_result or {},
            )

            self._emit_outbox_event(
                user_id=ctx.user_id,
                entry_id=ctx.entry_id,
                processing_job_id=ctx.job_id,
                processing_run_id=ctx.processing_run_id,
                event_type="entry.processed",
                payload={
                    "entry_id": ctx.entry_id,
                    "job_id": ctx.job_id,
                    "processing_run_id": ctx.processing_run_id,
                    "result_type": "success",
                    "status": "completed",
                },
            )

            self._insert_attempt_row(
                processing_job_id=ctx.job_id,
                attempt_id=ctx.attempt_id,
                status="succeeded",
                payload_hash=_sha256_hex(result),
                duration_ms=result["processing_duration_ms"],
            )
            job.status = "succeeded"
            job.attempt_count = max(job.attempt_count, ctx.attempt_id)
            job.finalized_at = _now_utc()
            job.final_payload_hash = _sha256_hex(result)
            job.final_error_code = None
            job.final_error_message = None
            job.result_json = json.dumps(result, sort_keys=True)
            job.updated_at = _now_utc()
            self._mark_claim_completed(ctx.user_id, idempotency_key, job)
            db.commit()
            return result

    def _build_success_result(
        self,
        *,
        ctx: PipelineContext,
        structured: dict[str, Any],
        plan: dict[str, Any],
        progress: dict[str, Any],
        skill_awards: dict[str, Any],
        theme_awards: dict[str, Any],
        progression_out: dict[str, Any],
        harmony_out: dict[str, Any],
        strategy_out: dict[str, Any],
        variety_out: dict[str, Any],
        insight_out: dict[str, Any],
        anomaly_out: dict[str, Any],
        personality_out: dict[str, Any],
        persisted_personality_messages: list[dict[str, Any]],
        summary: dict[str, Any],
        finalize: dict[str, Any],
        story_arc_out: dict[str, Any] | None = None,
        quest_matcher_out: dict[str, Any] | None = None,
        report_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cache_stats = self.cache.get_stats()
        fallbacks = [m for m in ctx.step_metrics if m.status == "fallback"]
        succeeded = [m for m in ctx.step_metrics if m.status == "succeeded"]
        structured_data = dict(plan["structured_data"])
        structured_data["structured_id"] = structured["structured_id"]
        quality = _build_quality_payload(ctx, cache_stats=cache_stats)
        step_trace = _build_step_trace(ctx, quality=quality)
        primary_message = _pick_primary_personality_message(
            persisted_personality_messages
        )
        quest_progression = dict((quest_matcher_out or {}).get("progression", {}) or {})
        summary_payload = dict(summary)
        summary_payload["detected_skills"] = list(
            structured_data.get("resolved_skill_names")
            or plan["detection"].get("detected_skills", [])
        )
        summary_payload["detected_activities"] = list(
            plan["detection"].get("detected_activities", [])
        )
        summary_payload["source_skill_ids"] = sorted(
            structured_data.get("source_skills_weights_bp", {}).keys()
        )
        summary_payload["final_xp_target_skill_ids"] = list(
            (quest_matcher_out or {}).get("xp_lineage", {}).get(
                "final_target_skill_ids", []
            )
        )
        skill_updates = [
            {
                "updated_skills": progression_out.get("updated_skills", 0),
                "xp_results": progression_out.get("xp_results", {}),
            }
        ]
        theme_updates = [
            {"updated_themes": progression_out.get("updated_themes", 0)}
        ]
        if quest_progression:
            skill_updates.append(
                {
                    "source": "quest_matcher",
                    "updated_skills": quest_progression.get("updated_skills", 0),
                    "xp_results": quest_progression.get("xp_results", {}),
                }
            )
            theme_updates.append(
                {
                    "source": "quest_matcher",
                    "updated_themes": quest_progression.get("updated_themes", 0),
                }
            )

        personality_result = {
            "personality": personality_out.get("personality"),
            "selection_reason": personality_out.get("selection_reason"),
            "message": (
                str(primary_message.get("message_text", ""))
                if primary_message is not None
                else personality_out.get("message", "")
            ),
            "message_id": (
                str(primary_message.get("id"))
                if primary_message is not None and primary_message.get("id") is not None
                else personality_out.get("message_id")
            ),
            "generation_mode": personality_out.get(
                "generation_mode",
                (personality_out.get("context_data", {}) or {}).get(
                    "generation_mode", "template"
                ),
            ),
            "citations": list(
                personality_out.get(
                    "citations",
                    (personality_out.get("context_data", {}) or {}).get("citations", []),
                )
                or []
            ),
            "fallback_reason": personality_out.get(
                "fallback_reason",
                (personality_out.get("context_data", {}) or {}).get("fallback_reason"),
            ),
            "template_key": personality_out.get(
                "template_key",
                (personality_out.get("context_data", {}) or {}).get("template_key"),
            ),
            "inserted": personality_out.get("inserted"),
            "context_data": dict(personality_out.get("context_data", {}) or {}),
        }
        provenance = _build_provenance_payload(ctx, quality=quality)
        provenance["insight"] = {
            "prompt_inputs": dict(insight_out.get("prompt_inputs", {}) or {}),
            "generation_mode": insight_out.get("generation_mode"),
            "suppression_reason": insight_out.get("suppression_reason"),
            "citations": list(insight_out.get("citations", []) or []),
        }
        provenance["personality"] = {
            "generation_mode": personality_result.get("generation_mode"),
            "fallback_reason": personality_result.get("fallback_reason"),
            "template_key": personality_result.get("template_key"),
            "citations": personality_result.get("citations", []),
        }

        payload = asdict(
            EntryProcessingSuccessResult(
                entry_id=ctx.entry_id,
                user_id=ctx.user_id,
                created_at_utc=ctx.time.created_at_utc,
                processing_started_at_utc=ctx.time.processing_started_at_utc,
                processing_completed_at_utc=ctx.time.processing_completed_at_utc or "",
                local_event_date=ctx.time.local_event_date,
                structured_data=structured_data,
                quests_created=list((quest_matcher_out or {}).get("created_quests", [])),
                quests_completed=list((quest_matcher_out or {}).get("completed_quests", [])),
                quests_progressed=list((quest_matcher_out or {}).get("progressed_quests", [])),
                xp_awards=(
                    list(skill_awards["skill_awards"])
                    + list(theme_awards["theme_awards"])
                    + list((quest_matcher_out or {}).get("xp_awards", []))
                ),
                level_ups=[],
                skill_updates=skill_updates,
                theme_updates=theme_updates,
                harmony_status=harmony_out,
                strategy_detected=(
                    strategy_out.get("detected_strategies") or [None]
                )[0],
                variety_bonus=float(variety_out.get("variety_bonus_pct", 0.0)),
                insights_discovered=(
                    [insight_out] if insight_out.get("insight_id") else []
                ),
                arc_updates=list((story_arc_out or {}).get("arc_updates", [])),
                anomaly_score=float(anomaly_out.get("score", 0.0)),
                troll_multiplier=float(anomaly_out.get("troll_multiplier", 1.0)),
                personality_messages=persisted_personality_messages,
                active_personality=(
                    primary_message.get("personality")
                    if primary_message is not None
                    else personality_out.get("personality")
                ),
                processing_duration_ms=int(finalize.get("processing_duration_ms", 0)),
                steps_attempted=len(ctx.step_metrics),
                steps_succeeded=len(succeeded),
                steps_fallbacked=len(fallbacks),
                noncritical_errors=[asdict(err) for err in ctx.noncritical_errors],
                pipeline_version=ctx.versions.pipeline_version,
                ruleset_version=ctx.versions.ruleset_version,
                config_version=ctx.versions.config_version,
                processing_run_id=ctx.processing_run_id,
                job_id=ctx.job_id,
                poll_path=f"/api/v1/entry-jobs/{ctx.job_id}",
                summary=summary_payload,
                message=personality_result["message"],
                message_id=personality_result["message_id"],
                personality=personality_result["personality"],
                meta=quality,
                step_trace=step_trace,
                quality=quality,
                provenance=provenance,
                insight_result=dict(insight_out),
                personality_result=personality_result,
                report_result=report_result or {},
            )
        )
        payload["status"] = "completed"
        payload["quest_result"] = quest_matcher_out or {}
        return payload

    def _build_failure_result(
        self,
        *,
        ctx: PipelineContext,
        error_code: str,
        message: str,
    ) -> dict[str, Any]:
        completed_at = _iso8601z(_now_utc())
        ctx.time.processing_completed_at_utc = completed_at
        quality = _build_quality_payload(ctx)
        step_trace = _build_step_trace(ctx, quality=quality)
        provenance = _build_provenance_payload(ctx, quality=quality)
        if ctx.terminal_error is None:
            ctx.terminal_error = ErrorRecord(
                step="entry_pipeline",
                code=error_code,
                category="db" if "DB" in error_code else "invariant",
                retryable=False,
                severity="critical",
                message=message,
            )
        return asdict(
            EntryProcessingFailureResult(
                entry_id=ctx.entry_id,
                user_id=ctx.user_id,
                created_at_utc=ctx.time.created_at_utc,
                processing_started_at_utc=ctx.time.processing_started_at_utc,
                processing_completed_at_utc=completed_at,
                local_event_date=ctx.time.local_event_date,
                terminal_error=asdict(ctx.terminal_error),
                noncritical_errors=[asdict(err) for err in ctx.noncritical_errors],
                processing_duration_ms=max(
                    0,
                    int(
                        (
                            datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                            - datetime.fromisoformat(
                                ctx.time.processing_started_at_utc.replace(
                                    "Z", "+00:00"
                                )
                            )
                        ).total_seconds()
                        * 1000
                    ),
                ),
                pipeline_version=ctx.versions.pipeline_version,
                ruleset_version=ctx.versions.ruleset_version,
                config_version=ctx.versions.config_version,
                processing_run_id=ctx.processing_run_id,
                retry_allowed=False,
                retry_after_ms=None,
                job_id=ctx.job_id,
                poll_path=f"/api/v1/entry-jobs/{ctx.job_id}",
                step_trace=step_trace,
                quality=quality,
                provenance=provenance,
            )
        )

    # ------------------------------------------------------------------
    # Idempotency & job tracking
    # ------------------------------------------------------------------

    def _insert_attempt_row(
        self,
        *,
        processing_job_id: str,
        attempt_id: int,
        status: str,
        payload_hash: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        db = self._db_handle()
        existing = (
            db.query(ProcessingJobAttempt)
            .filter(
                ProcessingJobAttempt.processing_job_id == processing_job_id,
                ProcessingJobAttempt.attempt_id == attempt_id,
            )
            .one_or_none()
        )
        if existing is not None:
            return
        db.add(
            ProcessingJobAttempt(
                processing_job_id=processing_job_id,
                attempt_id=attempt_id,
                attempted_at=_now_utc(),
                executor_type="server_local",
                node_id=None,
                status=status,
                payload_hash=payload_hash,
                error_code=error_code,
                error_message=error_message,
                duration_ms=duration_ms,
            )
        )
        job = db.query(ProcessingJob).filter(ProcessingJob.id == processing_job_id).one()
        job.attempt_count = max(job.attempt_count, attempt_id)
        db.flush()

    def _claim_idempotency(
        self,
        user_id: str,
        entry_id: str,
        key: str,
        processing_run_id: str,
        *,
        request_payload_hash: str | None = None,
    ) -> None:
        db = self._db_handle()
        db.add(
            EntryIdempotencyClaim(
                user_id=user_id,
                idempotency_key=key,
                request_payload_hash=request_payload_hash,
                entry_id=entry_id,
                processing_run_id=processing_run_id,
                status="reserved",
                updated_at=_now_utc(),
            )
        )
        db.flush()

    def _get_idempotent_replay(self, user_id: str, key: str) -> dict[str, Any] | None:
        with self._new_session() as db, self._use_db(db):
            claim = (
                db.query(EntryIdempotencyClaim)
                .filter(
                    EntryIdempotencyClaim.user_id == user_id,
                    EntryIdempotencyClaim.idempotency_key == key,
                )
                .one_or_none()
            )
            if claim is None:
                return None

            job = self._get_job(
                job_id=claim.processing_job_id,
                user_id=user_id,
                processing_run_id=claim.processing_run_id,
            )
            if job is not None:
                if job.result_json:
                    payload = json.loads(job.result_json)
                    payload["replayed"] = True
                    payload["idempotency_key"] = key
                    return payload
                payload = self._build_ack_payload(job, key, status="pending")
                payload["replayed"] = True
                return payload

            return {
                "result_type": "ack",
                "status": claim.status,
                "idempotency_key": key,
                "replayed": True,
                "processing_run_id": claim.processing_run_id,
                "entry_id": claim.entry_id,
            }

    def _upsert_job(
        self,
        user_id: str,
        entry_id: str,
        processing_run_id: str,
        *,
        job_id: str | None = None,
        request_payload_hash: str | None = None,
        versions: VersionSnapshot,
    ) -> ProcessingJob:
        db = self._db_handle()
        if job_id:
            existing = self._get_job(job_id=job_id, user_id=user_id)
            if existing is not None:
                existing.processing_run_id = processing_run_id
                existing.request_payload_hash = request_payload_hash
                existing.pipeline_version = versions.pipeline_version
                existing.ruleset_version = versions.ruleset_version
                existing.config_version = versions.config_version
                existing.status = "in_progress"
                db.flush()
                return existing

        job = ProcessingJob(
            id=job_id or str(uuid.uuid4()),
            user_id=user_id,
            entry_id=entry_id,
            step_name="entry_pipeline",
            processing_run_id=processing_run_id,
            status="in_progress",
            attempt_count=0,
            request_payload_hash=request_payload_hash,
            pipeline_version=versions.pipeline_version,
            ruleset_version=versions.ruleset_version,
            config_version=versions.config_version,
            ai_version_snapshot=json.dumps(
                versions.ai_models, sort_keys=True, separators=(",", ":")
            ),
            prompt_version_snapshot=json.dumps(
                versions.prompt_versions, sort_keys=True, separators=(",", ":")
            ),
        )
        db.add(job)
        db.flush()
        return job

    def _mark_claim_in_progress(
        self,
        *,
        user_id: str,
        key: str,
        entry_id: str,
        processing_job_id: str,
        processing_run_id: str,
        request_payload_hash: str | None = None,
    ) -> EntryIdempotencyClaim:
        db = self._db_handle()
        claim = (
            db.query(EntryIdempotencyClaim)
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
                request_payload_hash=request_payload_hash,
                entry_id=entry_id,
                processing_job_id=processing_job_id,
                processing_run_id=processing_run_id,
                status="in_progress",
                updated_at=_now_utc(),
            )
            db.add(claim)
        else:
            claim.entry_id = entry_id
            claim.processing_job_id = processing_job_id
            claim.processing_run_id = processing_run_id
            claim.request_payload_hash = request_payload_hash
            claim.status = "in_progress"
            claim.updated_at = _now_utc()
        db.flush()
        return claim

    def _mark_claim_completed(
        self,
        user_id: str,
        key: str,
        job: ProcessingJob,
    ) -> None:
        db = self._db_handle()
        claim = (
            db.query(EntryIdempotencyClaim)
            .filter(
                EntryIdempotencyClaim.user_id == user_id,
                EntryIdempotencyClaim.idempotency_key == key,
            )
            .one()
        )
        claim.status = "completed"
        claim.processing_job_id = job.id
        claim.processing_run_id = job.processing_run_id
        claim.updated_at = _now_utc()
        claim.completed_at = _now_utc()
        claim.final_error_code = None
        claim.result_pointer_json = json.dumps(
            self._terminal_result_pointer(job, status="completed"),
            sort_keys=True,
        )

    def _record_failure(
        self,
        *,
        job_id: str,
        user_id: str,
        entry_id: str,
        key: str,
        processing_run_id: str,
        request_payload_hash: str | None = None,
        error: str,
        error_code: str,
        failure_payload: dict[str, Any] | None = None,
        attempt_id: int | None = None,
    ) -> None:
        with self._new_session() as db, self._use_db(db):
            job = (
                db.query(ProcessingJob)
                .filter(ProcessingJob.id == job_id)
                .one_or_none()
            )
            processing_job_ref = job.id if job is not None else None
            payload = failure_payload or {
                "result_type": "failure",
                "status": "failed",
                "terminal_error": {
                    "step": "entry_pipeline",
                    "code": error_code,
                    "category": "db",
                    "retryable": False,
                    "severity": "critical",
                    "message": error,
                    "internal_details": None,
                },
                "noncritical_errors": [],
            }

            if job is not None:
                job.status = "failed"
                job.final_error_code = error_code
                job.final_error_message = error
                job.finalized_at = _now_utc()
                job.final_payload_hash = _sha256_hex(payload)
                job.result_json = json.dumps(payload, sort_keys=True)
                self._insert_attempt_row(
                    processing_job_id=job.id,
                    attempt_id=max(1, attempt_id or job.attempt_count + 1),
                    status="failed",
                    payload_hash=job.final_payload_hash,
                    error_code=error_code,
                    error_message=error,
                    duration_ms=payload.get("processing_duration_ms"),
                )

            claim = (
                db.query(EntryIdempotencyClaim)
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
                    request_payload_hash=request_payload_hash,
                    entry_id=entry_id,
                    processing_job_id=processing_job_ref,
                    processing_run_id=processing_run_id,
                    status="failed_terminal",
                    final_error_code=error_code,
                    updated_at=_now_utc(),
                )
                db.add(claim)
            else:
                claim.request_payload_hash = request_payload_hash
                claim.entry_id = entry_id
                claim.processing_job_id = processing_job_ref
                claim.processing_run_id = processing_run_id
                claim.status = "failed_terminal"
                claim.final_error_code = error_code
                claim.updated_at = _now_utc()
                claim.completed_at = _now_utc()

            if job is not None:
                claim.result_pointer_json = json.dumps(
                    self._terminal_result_pointer(job, status="failed_terminal"),
                    sort_keys=True,
                )

            entry = self._get_entry(user_id=user_id, entry_id=entry_id)
            if entry is not None:
                entry.status = "failed"
                entry.error_message = error
                entry.processed_at = _now_utc()

            self._emit_outbox_event(
                user_id=user_id,
                entry_id=entry_id,
                processing_job_id=processing_job_ref,
                processing_run_id=processing_run_id,
                event_type="entry.processing_failed",
                payload={
                    "entry_id": entry_id,
                    "job_id": job_id,
                    "processing_run_id": processing_run_id,
                    "error_code": error_code,
                    "result_type": "failure",
                },
            )
            db.commit()

    def _emit_outbox_event(
        self,
        *,
        user_id: str,
        entry_id: str | None,
        processing_job_id: str | None,
        processing_run_id: str | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        db = self._db_handle()
        dedupe_raw = f"{user_id}:{event_type}:{json.dumps(payload, sort_keys=True)}"
        dedupe = hashlib.sha256(dedupe_raw.encode("utf-8")).hexdigest()

        existing = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.event_dedupe_key == dedupe)
            .one_or_none()
        )
        if existing is not None:
            return

        db.add(
            OutboxEvent(
                user_id=user_id,
                entry_id=entry_id,
                processing_job_id=processing_job_id,
                processing_run_id=processing_run_id,
                event_type=event_type,
                event_dedupe_key=dedupe,
                destination="internal",
                payload_json=json.dumps(payload, sort_keys=True),
                payload_hash=_hash_json_payload(payload),
                status="pending",
            )
        )
        db.flush()

    def _upsert_claim_lease(
        self,
        *,
        user_id: str,
        entry_id: str,
        step_name: str,
        owner_kind: str,
        owner_id: str,
    ) -> ProcessingJobClaim:
        db = self._db_handle()
        claim = (
            db.query(ProcessingJobClaim)
            .filter(
                ProcessingJobClaim.user_id == user_id,
                ProcessingJobClaim.entry_id == entry_id,
                ProcessingJobClaim.step_name == step_name,
            )
            .one_or_none()
        )
        lease_token = str(uuid.uuid4())
        now = _now_utc()
        lease_expires_at = now + timedelta(minutes=5)

        if claim is None:
            claim = ProcessingJobClaim(
                user_id=user_id,
                entry_id=entry_id,
                step_name=step_name,
                owner_kind=owner_kind,
                owner_id=owner_id,
                lease_token=lease_token,
                lease_expires_at=lease_expires_at,
            )
            db.add(claim)
        else:
            claim.owner_kind = owner_kind
            claim.owner_id = owner_id
            claim.lease_token = lease_token
            claim.heartbeat_at = now
            claim.updated_at = now
            claim.lease_expires_at = lease_expires_at
        db.flush()
        return claim

    def _get_job(
        self,
        *,
        job_id: str | None,
        user_id: str,
        processing_run_id: str | None = None,
    ) -> ProcessingJob | None:
        db = self._db_handle()
        query = db.query(ProcessingJob).filter(ProcessingJob.user_id == user_id)
        if job_id is not None:
            return query.filter(ProcessingJob.id == job_id).one_or_none()
        if processing_run_id is not None:
            return query.filter(
                ProcessingJob.processing_run_id == processing_run_id,
                ProcessingJob.step_name == "entry_pipeline",
            ).one_or_none()
        return None

    def _build_ack_payload(
        self, job: ProcessingJob, idempotency_key: str, *, status: str = "pending"
    ) -> dict[str, Any]:
        return asdict(
            EntryProcessingAckResult(
                status=status,
                job_id=job.id,
                entry_id=job.entry_id,
                user_id=job.user_id,
                processing_run_id=job.processing_run_id,
                poll_path=f"/api/v1/entry-jobs/{job.id}",
                idempotency_key=idempotency_key,
                retryable=True,
                created_at_utc=_iso8601z(job.created_at),
                updated_at_utc=_iso8601z(job.updated_at),
                attempt_count=int(job.attempt_count or 0),
                last_error_code=job.final_error_code,
            )
        )

    def _terminal_result_pointer(
        self,
        job: ProcessingJob,
        *,
        status: str | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "job_id": job.id,
            "entry_id": job.entry_id,
            "status": status or ("completed" if job.status == "succeeded" else "pending"),
            "poll_path": f"/api/v1/entry-jobs/{job.id}",
            "terminal_result_hash": job.final_payload_hash,
        }

    def _build_job_status_payload(self, job: ProcessingJob) -> dict[str, Any]:
        base = {
            "status": "in_progress" if job.status == "in_progress" else (
                "completed" if job.status == "succeeded" else "failed_terminal"
            ),
            "job_id": job.id,
            "processing_run_id": job.processing_run_id,
            "entry_id": job.entry_id,
            "created_at_utc": _iso8601z(job.created_at),
            "updated_at_utc": _iso8601z(job.updated_at),
            "attempt_count": int(job.attempt_count or 0),
            "last_error_code": job.final_error_code,
        }
        if job.status == "in_progress":
            return {
                **base,
                "terminal_result": None,
                "terminal_result_pointer": self._terminal_result_pointer(
                    job, status="pending"
                ),
            }

        terminal_result = json.loads(job.result_json) if job.result_json else None
        return {
            **base,
            "terminal_result": terminal_result,
            "terminal_result_pointer": self._terminal_result_pointer(
                job, status=base["status"]
            ),
        }

    def _dispatch_outbox_for_run(self, processing_run_id: str) -> None:
        if self._session_factory is None:
            return
        with self._new_session() as db:
            rows = (
                db.query(OutboxEvent)
                .filter(
                    OutboxEvent.processing_run_id == processing_run_id,
                    OutboxEvent.status.in_(("pending", "failed_retryable")),
                )
                .order_by(OutboxEvent.created_at.asc())
                .all()
            )
            for row in rows:
                token = str(uuid.uuid4())
                now = _now_utc()
                row.status = "dispatching"
                row.lease_owner_token = token
                row.lease_expires_at = now + timedelta(minutes=1)
                row.updated_at = now
                row.status = "succeeded"
                row.dispatched_at = now
                row.lease_owner_token = None
                row.lease_expires_at = None
                row.updated_at = now
            db.commit()

    def _save_to_recovery(
        self,
        *,
        entry_id: str,
        user_id: str,
        idempotency_key: str,
        error: str,
        error_code: str,
    ) -> None:
        if self.recovery is None:
            logger.critical(
                "pipeline no recovery_queue configured - entry=%s user=%s will NOT be"
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
        db = self._db_handle()
        return (
            db.query(JournalEntry)
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
            recovery_cls = _compat_pipeline_attr("RecoveryQueue", RecoveryQueue)
            self._recovery: RecoveryQueue = recovery or recovery_cls()
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
            qdrant_cls = _compat_pipeline_attr(
                "QdrantClientAdapter", QdrantClientAdapter
            )
            if not isinstance(qdrant, qdrant_cls):
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
        strict_ai = str(
            getattr(self._processor, "_strict_ai_dependencies", "0")
            if hasattr(self._processor, "_strict_ai_dependencies")
            else "0"
        ).lower() in {"1", "true", "yes", "on"}
        error_codes: list[str] = []
        if not ollama_ok:
            error_codes.append("DEPENDENCY_OLLAMA_UNAVAILABLE")
        if not qdrant_ok:
            error_codes.append("DEPENDENCY_QDRANT_UNAVAILABLE")

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
            "ready": (ollama_ok and qdrant_ok) or not strict_ai,
            "strict_ai_dependencies": strict_ai,
            "error_codes": error_codes,
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
        job_id: str | None = None,
        processing_run_id: str | None = None,
        reserved_claim: bool = False,
        request_payload_hash: str | None = None,
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
                    self._processor.process_entry,
                    entry_id,
                    user_id,
                    key,
                    job_id=job_id,
                    processing_run_id=processing_run_id,
                    reserved_claim=reserved_claim,
                    request_payload_hash=request_payload_hash,
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
