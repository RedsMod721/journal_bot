"""
17-Step Entry Pipeline — Section 13.6 canonical implementation.

Transaction boundaries
----------------------
Steps 1–4  : Tx A prelude + Tx A commit  (< 200 ms total, no AI calls)
Steps 5–15 : Outside any transaction      (all AI / LLM / RAG / DB reads)
Step 16    : Tx B atomic commit           (< 500 ms, no network calls)
Step 17    : Post-commit outbox + result assembly

Logging namespaces
------------------
[pipeline:step]     Step lifecycle (start / end / fallback)
[pipeline:llm]      Any Ollama / LLM call
[pipeline:rag]      Any Qdrant / RAG operation
[pipeline:tx_a]     Transaction A lifecycle
[pipeline:tx_b]     Transaction B lifecycle
[pipeline:error]    Non-fatal degradation
[pipeline:fatal]    Terminal / critical failure
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Literal, Optional

from sqlalchemy.orm import Session

from src.ai.pipeline.idempotency_manager import IdempotencyManager
from src.ai.pipeline.pipeline_context import PipelineContext, create_pipeline_context
from src.ai.pipeline.transaction_orchestrator import (
    AlreadyFinalisedError,
    TransactionOrchestrator,
    TxAError,
    TxBError,
)
from src.core.entry_skill_resolver import resolve_entry_skill_signals

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "week7-v1"
RULESET_VERSION = "s10-v8"

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PipelineSuccessResult:
    result_type: Literal["success"] = "success"
    entry_id: str = ""
    user_id: str = ""
    status: Literal["completed"] = "completed"
    created_at_utc: str = ""
    processing_started_at_utc: str = ""
    processing_completed_at_utc: str = ""
    local_event_date: str = ""
    structured_data: Dict[str, Any] = field(default_factory=dict)
    safety_result: Dict[str, Any] = field(default_factory=dict)
    forgiveness_result: Dict[str, Any] = field(default_factory=dict)
    strategy_result: Dict[str, Any] = field(default_factory=dict)
    variety_result: Dict[str, Any] = field(default_factory=dict)
    quest_result: Dict[str, Any] = field(default_factory=dict)
    anomaly_result: Dict[str, Any] = field(default_factory=dict)
    harmony_result: Dict[str, Any] = field(default_factory=dict)
    insight_result: Dict[str, Any] = field(default_factory=dict)
    arc_result: Dict[str, Any] = field(default_factory=dict)
    xp_result: Dict[str, Any] = field(default_factory=dict)
    personality_result: Dict[str, Any] = field(default_factory=dict)
    report_result: Dict[str, Any] = field(default_factory=dict)
    personality_messages: List[Dict[str, Any]] = field(default_factory=list)
    active_personality: Optional[str] = None
    message: str = ""
    message_id: Optional[str] = None
    personality: Optional[str] = None
    processing_duration_ms: int = 0
    steps_attempted: int = 0
    steps_succeeded: int = 0
    steps_fallbacked: int = 0
    noncritical_errors: List[Dict[str, Any]] = field(default_factory=list)
    pipeline_version: str = ""
    ruleset_version: str = ""
    processing_run_id: str = ""
    job_id: str = ""
    degraded: bool = False
    degraded_codes: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    step_trace: List[Dict[str, Any]] = field(default_factory=list)
    quality: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineFailureResult:
    result_type: Literal["failure"] = "failure"
    entry_id: Optional[str] = None
    user_id: str = ""
    created_at_utc: Optional[str] = None
    processing_started_at_utc: str = ""
    processing_completed_at_utc: str = ""
    local_event_date: Optional[str] = None
    status: Literal["failed"] = "failed"
    error_code: str = ""
    error_message: str = ""
    step: str = ""
    terminal_error: Dict[str, Any] = field(default_factory=dict)
    noncritical_errors: List[Dict[str, Any]] = field(default_factory=list)
    processing_duration_ms: int = 0
    pipeline_version: str = PIPELINE_VERSION
    ruleset_version: str = RULESET_VERSION
    processing_run_id: Optional[str] = None
    job_id: Optional[str] = None
    retry_allowed: bool = False
    retry_after_ms: Optional[int] = None
    poll_path: Optional[str] = None
    step_trace: List[Dict[str, Any]] = field(default_factory=list)
    quality: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Fallback artifact builders (Section 11.8.1)
# ---------------------------------------------------------------------------


def _fallback_structured_data(error_code: str, now_iso: str) -> Dict[str, Any]:
    """Deterministic fallback for step 5 (categorization failure)."""
    return {
        "canonical_text": "",
        "primary_action_type": None,
        "dominant_emotions": [],
        "energy_level": None,
        "self_compassion_score": None,
        "task_type": "unknown",
        "skills_themes_involved": [],
        "safety_flags": [],
        "source_skills_weights_bp": {},
        "skills_weights_bp": {},
        "resolved_skill_names": [],
        "extraction_confidence_score": 0.0,
        "pattern_hits_json": [],
        "extraction_status": "fallback",
        "extraction_error_code": error_code,
        "extracted_at": now_iso,
        "fallback_used": True,
    }


def _fallback_safety(error_code: str) -> Dict[str, Any]:
    """Fallback for step 6 — safe/neutral classification."""
    return {
        "risk_level": "none",
        "force_therapist": False,
        "sentiment_score": 50,
        "safety_flags": [],
        "fallback_used": True,
        "error_code": error_code,
    }


def _fallback_forgiveness(error_code: str) -> Dict[str, Any]:
    """Fallback for step 7 — skip forgiveness update."""
    return {
        "preset": None,
        "updates_applied": 0,
        "fallback_used": True,
        "error_code": error_code,
    }


def _fallback_balance(error_code: str) -> Dict[str, Any]:
    """Fallback for step 8 — neutral strategy / zero variety bonus."""
    return {
        "detected_strategies": [],
        "strategy_scores": {},
        "diminishing_multiplier": 1.0,
        "diminishing_bp": 10000,
        "variety_score": 0.0,
        "variety_bonus_pct": 0.0,
        "variety_multiplier_bp": 10000,
        "fallback_used": True,
        "error_code": error_code,
    }


def _fallback_quest(error_code: str) -> Dict[str, Any]:
    """Fallback for step 9 — zero quests, zero failure penalty."""
    return {
        "instant_quest_id": None,
        "streak_quest_ids": [],
        "created_quests": [],
        "progressed_quests": [],
        "completed_quests": [],
        "xp_awards": [],
        "xp_award_count": 0,
        "total_xp_awarded": 0,
        "failure_penalty_xp": 0,
        "fallback_used": True,
        "error_code": error_code,
    }


def _fallback_anomaly(error_code: str) -> Dict[str, Any]:
    """Fallback for step 10 — neutral score, 1.0× troll multiplier."""
    return {
        "anomaly_score": 0.0,
        "score": 0.0,
        "troll_multiplier": 1.0,
        "troll_bp": 10000,
        "detection_factors": {},
        "reasons": [],
        "fallback_used": True,
        "error_code": error_code,
    }


def _fallback_harmony(error_code: str) -> Dict[str, Any]:
    """Fallback for step 11 — last-known snapshot or neutral."""
    return {
        "dimensions_addressed": [],
        "overall_balance": 0.5,
        "overwork_stage": 0,
        "fallback_used": True,
        "error_code": error_code,
    }


def _fallback_insight(user_id: str, entry_id: str, error_code: str) -> Dict[str, Any]:
    """Fallback for step 12 — empty insights, pipeline continues."""
    return {
        "user_id": user_id,
        "entry_id": entry_id,
        "insights": [],
        "insight_id": None,
        "insight_text": "",
        "insight_category": "general",
        "insight_confidence": 0.0,
        "from_ollama": False,
        "from_cache": False,
        "rag_hits": [],
        "generated": False,
        "persisted": False,
        "generation_mode": "suppressed",
        "suppression_reason": error_code,
        "citations": [],
        "prompt_inputs": {},
        "fallback_used": True,
        "error_code": error_code,
    }


def _fallback_arc(error_code: str) -> Dict[str, Any]:
    """Fallback for step 13 — arc_multiplier 1.0, no arc progression."""
    return {
        "active_arc": None,
        "arc_updates": [],
        "arc_multiplier": 1.0,
        "arc_multiplier_bp": 10000,
        "notes": [],
        "fallback_used": True,
        "error_code": error_code,
    }


def _fallback_xp(error_code: str) -> Dict[str, Any]:
    """
    Step 14 is CRITICAL — this is only used when _marking_ the failure.
    XP formula failure terminates the pipeline.
    """
    return {
        "awards": [],
        "total_xp": 0,
        "updated_skills": 0,
        "updated_themes": 0,
        "fallback_used": True,
        "error_code": error_code,
    }


def _fallback_personality(error_code: str) -> Dict[str, Any]:
    """Fallback for step 15 — neutral observer message."""
    return {
        "personality": "observer",
        "selection_reason": "degraded_fallback",
        "selection_factors": {},
        "message": "[OBS] Entry recorded.",
        "message_type": "entry_ack",
        "context_data": {},
        "citations": [],
        "message_id": None,
        "generation_mode": "safe_fallback",
        "fallback_reason": error_code,
        "template_key": "observer.safe_fallback",
        "fallback_used": True,
        "error_code": error_code,
    }


def _fallback_system_report(error_code: str) -> Dict[str, Any]:
    """Fallback for step 15b — minimal system report on generation failure."""
    return {
        "personality": "system",
        "message_type": "report_summary",
        "message_text": "[SYSTEM] Report generation failed.",
        "logical_slot_key": "system_report",
        "selector_version": 1,
        "context_data": {},
        "fallback_used": True,
        "error_code": error_code,
    }


# ---------------------------------------------------------------------------
# Step runner
# ---------------------------------------------------------------------------


@dataclass
class _StepRecord:
    step_name: str
    status: str  # succeeded | fallback | suppressed | failed_critical
    duration_ms: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    critical: bool = False
    fallback_used: bool = False
    output: Any = None
    not_persisted_reason: Optional[str] = None


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return str(value)


def _manual_step_record(
    *,
    step_name: str,
    output: Any,
    critical: bool,
    not_persisted_reason: Optional[str] = None,
) -> _StepRecord:
    return _StepRecord(
        step_name=step_name,
        status="succeeded",
        duration_ms=0,
        critical=critical,
        fallback_used=False,
        output=_json_safe(output),
        not_persisted_reason=not_persisted_reason,
    )


def _build_step_trace(records: List[_StepRecord]) -> List[Dict[str, Any]]:
    return [
        {
            "step_name": record.step_name,
            "status": record.status,
            "duration_ms": int(record.duration_ms),
            "critical": bool(record.critical),
            "fallback_used": bool(record.fallback_used),
            "error_code": record.error_code,
            "error_message": record.error_message,
            "output": _json_safe(record.output),
            "not_persisted_reason": record.not_persisted_reason,
        }
        for record in records
    ]


def _build_quality_payload(records: List[_StepRecord]) -> Dict[str, Any]:
    degraded_codes: List[str] = []
    for code in (
        record.error_code for record in records if record.status in {"fallback", "suppressed"}
    ):
        if code and code not in degraded_codes:
            degraded_codes.append(code)
    dependency_states = {
        "ollama": "degraded"
        if any(code and "OLLAMA" in code for code in degraded_codes)
        else "ok",
        "qdrant": "degraded"
        if any(code and ("QDRANT" in code or "RAG" in code) for code in degraded_codes)
        else "ok",
        "rag": "empty_or_unavailable"
        if any(code and ("QDRANT" in code or "RAG" in code) for code in degraded_codes)
        else "ok",
    }
    return {
        "degraded": bool(degraded_codes),
        "degraded_codes": degraded_codes,
        "dependency_states": dependency_states,
    }


def _build_provenance_payload(
    *,
    ctx: PipelineContext,
    quality: Dict[str, Any],
    insight_result: Dict[str, Any],
    personality_result: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "processing_run_id": ctx.processing_run_id,
        "pipeline_version": PIPELINE_VERSION,
        "ruleset_version": RULESET_VERSION,
        "quality_codes": list(quality.get("degraded_codes", [])),
        "time_snapshot": {
            "created_at_utc": _iso_z(ctx.time.created_at_utc),
            "processing_started_at_utc": _iso_z(ctx.time.processing_started_at_utc),
            "local_event_date": ctx.time.local_event_date,
            "user_timezone_at_ingest": ctx.time.user_timezone_at_ingest,
        },
        "version_snapshot": ctx.versions.as_json_dict(),
        "insight": {
            "generation_mode": insight_result.get("generation_mode"),
            "suppression_reason": insight_result.get("suppression_reason"),
            "citations": insight_result.get("citations", []),
            "prompt_inputs": insight_result.get("prompt_inputs", {}),
        },
        "personality": {
            "generation_mode": personality_result.get("generation_mode"),
            "fallback_reason": personality_result.get("fallback_reason"),
            "template_key": personality_result.get("template_key"),
            "citations": personality_result.get("citations", []),
        },
    }


def _build_summary_payload(
    *,
    structured_data: Dict[str, Any],
    strategy_result: Dict[str, Any],
    variety_result: Dict[str, Any],
    quest_result: Dict[str, Any],
    anomaly_result: Dict[str, Any],
    insight_result: Dict[str, Any],
    xp_result: Dict[str, Any],
) -> Dict[str, Any]:
    detected_activities = []
    primary_action_type = structured_data.get("primary_action_type")
    if primary_action_type:
        detected_activities.append(primary_action_type)
    final_xp_target_skill_ids = sorted(
        {
            award.get("skill_id")
            for award in xp_result.get("skill_awards", [])
            if award.get("skill_id")
        }
    )
    return {
        "anomaly_score": anomaly_result.get("anomaly_score", anomaly_result.get("score", 0.0)),
        "completed_quest_count": len(quest_result.get("completed_quests", [])),
        "detected_activities": detected_activities,
        "detected_skills": structured_data.get("resolved_skill_names")
        or structured_data.get("skills_themes_involved", []),
        "detected_strategies": strategy_result.get("detected_strategies", []),
        "insight_text": insight_result.get("insight_text"),
        "rag_hit_count": insight_result.get(
            "rag_hit_count", len(insight_result.get("rag_hits", []))
        ),
        "skill_award_count": len(xp_result.get("skill_awards", [])),
        "theme_award_count": len(xp_result.get("theme_awards", [])),
        "troll_multiplier": anomaly_result.get("troll_multiplier", 1.0),
        "variety_multiplier_bp": variety_result.get(
            "variety_multiplier_bp",
            strategy_result.get("variety_multiplier_bp", 10000),
        ),
        "variety_score": variety_result.get(
            "variety_score", strategy_result.get("variety_score", 0.0)
        ),
        "source_skill_ids": list((structured_data.get("source_skills_weights_bp") or {}).keys()),
        "final_xp_target_skill_ids": final_xp_target_skill_ids,
    }


def _build_xp_lineage(
    *,
    structured_data: Dict[str, Any],
    xp_result: Dict[str, Any],
) -> Dict[str, Any]:
    final_awards = [
        {
            "skill_id": award.get("skill_id"),
            "amount": award.get("amount"),
            "xp_reason": award.get("xp_reason"),
        }
        for award in xp_result.get("skill_awards", [])
        if award.get("skill_id")
    ]
    final_target_skill_ids = sorted(
        {award["skill_id"] for award in final_awards if award.get("skill_id")}
    )
    return {
        "resolved_skill_names": structured_data.get("resolved_skill_names", []),
        "source_skill_weights_bp": structured_data.get("source_skills_weights_bp", {}),
        "user_skill_weights_bp": structured_data.get("skills_weights_bp", {}),
        "pattern_hits_json": structured_data.get("pattern_hits_json", []),
        "final_awards": final_awards,
        "final_target_skill_ids": final_target_skill_ids,
        "redirect_paths": [
            {
                "source_skill_id": source_skill_id,
                "final_target_skill_ids": final_target_skill_ids,
            }
            for source_skill_id in (structured_data.get("source_skills_weights_bp") or {})
        ],
    }


def _run_step(
    *,
    ctx: PipelineContext,
    step_name: str,
    error_code: str,
    critical: bool,
    fn: Callable[[], Any],
    fallback_fn: Optional[Callable[[Exception], Any]] = None,
    records: List[_StepRecord],
) -> Any:
    """
    Execute *fn* and handle degradation per Section 11.8.1.

    - critical=True  + no fallback → raises, terminates pipeline
    - critical=False + fallback     → logs warning, returns fallback artifact
    - critical=False + no fallback  → logs warning, returns None
    """
    started = time.perf_counter()
    log_ctx = {
        "pipeline_ctx": {
            "user_id": ctx.user_id,
            "entry_id": ctx.entry_id,
            "run_id": ctx.processing_run_id,
            "step": step_name,
        }
    }
    logger.info(
        "[pipeline:step] START step=%s entry=%s run=%s",
        step_name,
        ctx.entry_id,
        ctx.processing_run_id,
        extra=log_ctx,
    )
    try:
        result = fn()
        duration_ms = int((time.perf_counter() - started) * 1000)
        status = "suppressed" if isinstance(result, dict) and result.get("suppression_reason") else "succeeded"
        records.append(
            _StepRecord(
                step_name=step_name,
                status=status,
                duration_ms=duration_ms,
                critical=critical,
                fallback_used=bool(isinstance(result, dict) and result.get("fallback_used")),
                output=_json_safe(result),
            )
        )
        logger.info(
            "[pipeline:step] OK step=%s entry=%s duration_ms=%d",
            step_name,
            ctx.entry_id,
            duration_ms,
            extra=log_ctx,
        )
        return result

    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)

        if critical and fallback_fn is None:
            records.append(
                _StepRecord(
                    step_name=step_name,
                    status="failed_critical",
                    duration_ms=duration_ms,
                    error_code=error_code,
                    error_message=str(exc),
                    critical=True,
                )
            )
            logger.error(
                "[pipeline:fatal] CRITICAL step=%s error_code=%s entry=%s: %s",
                step_name,
                error_code,
                ctx.entry_id,
                exc,
                extra=log_ctx,
            )
            ctx.add_error(step_name, error_code, str(exc), fatal=True)
            raise

        ctx.add_error(step_name, error_code, str(exc), fatal=False)

        if fallback_fn is not None:
            fallback_result = fallback_fn(exc)
            records.append(
                _StepRecord(
                    step_name=step_name,
                    status="fallback",
                    duration_ms=duration_ms,
                    error_code=error_code,
                    error_message=str(exc),
                    critical=critical,
                    fallback_used=True,
                    output=_json_safe(fallback_result),
                )
            )
            logger.warning(
                "[pipeline:error] FALLBACK step=%s error_code=%s entry=%s: %s",
                step_name,
                error_code,
                ctx.entry_id,
                exc,
                extra=log_ctx,
            )
            return fallback_result

        records.append(
            _StepRecord(
                step_name=step_name,
                status="suppressed",
                duration_ms=duration_ms,
                error_code=error_code,
                error_message=str(exc),
                critical=critical,
                output=None,
                not_persisted_reason="step returned no artifact",
            )
        )
        logger.warning(
            "[pipeline:error] NONCRITICAL step=%s error_code=%s entry=%s: %s",
            step_name,
            error_code,
            ctx.entry_id,
            exc,
            extra=log_ctx,
        )
        return None


# ---------------------------------------------------------------------------
# EntryPipeline — canonical 17-step orchestrator
# ---------------------------------------------------------------------------


class EntryPipeline:
    """
    Canonical 17-step entry processing pipeline (Section 13.6).

    Usage::

        pipeline = EntryPipeline(
            db=db,
            ollama=ollama_client,
            qdrant=qdrant_client,
            cache=step_cache,
        )
        result = pipeline.process(
            user_id=user_id,
            content=raw_text,
            idempotency_key=key,
        )
    """

    def __init__(
        self,
        db: Session,
        ollama: Any = None,
        qdrant: Any = None,
        cache: Any = None,
    ) -> None:
        self.db = db
        self.ollama = ollama
        self.qdrant = qdrant
        self.cache = cache
        self._idempotency_mgr = IdempotencyManager(db)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def process(
        self,
        *,
        user_id: str,
        content: str,
        idempotency_key: str,
        user_timezone: str = "UTC",
    ) -> Dict[str, Any]:
        """
        Execute all 17 pipeline steps and return a JSON-serialisable result dict.

        Returns either a PipelineSuccessResult or PipelineFailureResult as dict.
        """
        pipeline_start = time.perf_counter()
        processing_run_id = str(uuid.uuid4())
        records: List[_StepRecord] = []
        ctx: Optional[PipelineContext] = None
        tx_ids: Optional[Dict[str, str]] = None

        log_ctx = {
            "pipeline": {
                "user_id": user_id,
                "run_id": processing_run_id,
            }
        }

        logger.info(
            "[pipeline:step] PIPELINE_START user=%s run=%s",
            user_id,
            processing_run_id,
            extra=log_ctx,
        )

        try:
            # ──────────────────────────────────────────────────────────
            # STEP 1 — Request validation
            # ──────────────────────────────────────────────────────────
            logger.info("[pipeline:step] STEP_01 request_validation run=%s", processing_run_id)
            self._step_01_validate(user_id=user_id, content=content, idempotency_key=idempotency_key)
            records.append(
                _manual_step_record(
                    step_name="step_01_validate_input",
                    output={
                        "user_id": user_id,
                        "content_length": len(content),
                        "idempotency_key": idempotency_key,
                    },
                    critical=True,
                )
            )

            # ──────────────────────────────────────────────────────────
            # STEP 2 — Time & version snapshots
            # Captured once here; never re-read during the run.
            # ──────────────────────────────────────────────────────────
            logger.info("[pipeline:step] STEP_02 time_version_snapshots run=%s", processing_run_id)
            now_utc = datetime.now(timezone.utc)
            ctx = create_pipeline_context(
                user_id=user_id,
                entry_id="",          # filled in after Tx A
                processing_run_id=processing_run_id,
                idempotency_key=idempotency_key,
                user_timezone=user_timezone,
                created_at_utc=now_utc,
            )
            logger.debug(
                "[pipeline:llm] version_snapshot captured model=%s:%s run=%s",
                ctx.versions.ai_model_id,
                ctx.versions.ai_model_version,
                processing_run_id,
            )
            records.append(
                _manual_step_record(
                    step_name="step_02_capture_snapshots",
                    output={
                        "created_at_utc": _iso_z(ctx.time.created_at_utc),
                        "processing_started_at_utc": _iso_z(ctx.time.processing_started_at_utc),
                        "local_event_date": ctx.time.local_event_date,
                        "version_snapshot": ctx.versions.as_json_dict(),
                    },
                    critical=True,
                )
            )

            # ──────────────────────────────────────────────────────────
            # STEP 3 — Idempotency reservation
            # ──────────────────────────────────────────────────────────
            logger.info("[pipeline:step] STEP_03 idempotency_reservation run=%s", processing_run_id)
            replay = self._step_03_idempotency_check(user_id=user_id, idempotency_key=idempotency_key)
            if replay is not None:
                logger.info(
                    "[pipeline:step] IDEMPOTENT_REPLAY user=%s key=%s run=%s",
                    user_id,
                    idempotency_key,
                    processing_run_id,
                )
                return replay
            records.append(
                _manual_step_record(
                    step_name="step_03_reserve_idempotency",
                    output={
                        "user_id": user_id,
                        "idempotency_key": idempotency_key,
                        "replayed": False,
                    },
                    critical=True,
                )
            )

            # ──────────────────────────────────────────────────────────
            # STEP 4 — Create/load entry + initialise processing job (Tx A)
            # ──────────────────────────────────────────────────────────
            logger.info("[pipeline:tx_a] STEP_04 tx_a_start run=%s", processing_run_id)
            orchestrator = TransactionOrchestrator(self.db)
            try:
                tx_ids = orchestrator.execute_tx_a(
                    user_id=user_id,
                    content=content,
                    idempotency_key=idempotency_key,
                    step_name="entry_pipeline",
                )
            except TxAError as exc:
                logger.error("[pipeline:fatal] TX_A_FAILED run=%s: %s", processing_run_id, exc)
                self._idempotency_mgr.fail(
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    error_code="TX_A_ERROR",
                    terminal=False,
                )
                quality = _build_quality_payload(records)
                return asdict(
                    PipelineFailureResult(
                        user_id=user_id,
                        created_at_utc=_iso_z(ctx.time.created_at_utc),
                        processing_started_at_utc=_iso_z(ctx.time.processing_started_at_utc),
                        processing_completed_at_utc=_iso_z(ctx.time.processing_started_at_utc),
                        local_event_date=ctx.time.local_event_date,
                        error_code="TX_A_ERROR",
                        error_message=str(exc),
                        step="step_04_tx_a",
                        terminal_error={
                            "code": "TX_A_ERROR",
                            "message": str(exc),
                            "step": "step_04_tx_a",
                            "retryable": False,
                        },
                        pipeline_version=PIPELINE_VERSION,
                        ruleset_version=RULESET_VERSION,
                        processing_run_id=processing_run_id,
                        step_trace=_build_step_trace(records),
                        quality=quality,
                        provenance={
                            "processing_run_id": processing_run_id,
                            "pipeline_version": PIPELINE_VERSION,
                            "ruleset_version": RULESET_VERSION,
                            "quality_codes": list(quality.get("degraded_codes", [])),
                            "version_snapshot": ctx.versions.as_json_dict(),
                        },
                    )
                )

            entry_id = tx_ids["entry_id"]
            job_id = tx_ids["job_id"]
            logger.info(
                "[pipeline:tx_a] TX_A_COMMITTED entry=%s job=%s run=%s",
                entry_id,
                job_id,
                processing_run_id,
            )
            records.append(
                _manual_step_record(
                    step_name="step_04_tx_a_create_job",
                    output={"entry_id": entry_id, "job_id": job_id, "step_name": "entry_pipeline"},
                    critical=True,
                )
            )

            # Advance idempotency claim to in_progress now that entry/job IDs exist.
            self._idempotency_mgr.advance_to_in_progress(
                user_id=user_id,
                idempotency_key=idempotency_key,
                entry_id=entry_id,
                job_id=job_id,
                processing_run_id=processing_run_id,
            )

            # Rebuild ctx with the real entry_id now that Tx A has committed.
            ctx = create_pipeline_context(
                user_id=user_id,
                entry_id=entry_id,
                processing_run_id=processing_run_id,
                idempotency_key=idempotency_key,
                user_timezone=user_timezone,
                created_at_utc=now_utc,
            )

            # ──────────────────────────────────────────────────────────
            # STEPS 5–15 — outside any transaction
            # ──────────────────────────────────────────────────────────
            self._run_steps_5_to_15(
                ctx=ctx,
                content=content,
                records=records,
            )

            # ──────────────────────────────────────────────────────────
            # STEP 16 — Finalise writes (Tx B)
            # ──────────────────────────────────────────────────────────
            logger.info(
                "[pipeline:tx_b] STEP_16 tx_b_start entry=%s job=%s run=%s",
                entry_id,
                job_id,
                processing_run_id,
            )
            try:
                orchestrator.execute_tx_b(entry_id=entry_id, job_id=job_id, pipeline_context=ctx)
            except AlreadyFinalisedError:
                logger.warning(
                    "[pipeline:tx_b] ALREADY_FINALISED entry=%s job=%s run=%s — returning replay",
                    entry_id,
                    job_id,
                    processing_run_id,
                )
                return self._build_already_finalised_result(ctx=ctx, entry_id=entry_id, job_id=job_id)
            except TxBError as exc:
                logger.error(
                    "[pipeline:fatal] TX_B_FAILED entry=%s job=%s run=%s: %s",
                    entry_id,
                    job_id,
                    processing_run_id,
                    exc,
                )
                self._try_mark_failed(
                    orchestrator=orchestrator,
                    job_id=job_id,
                    entry_id=entry_id,
                    error_code="TX_B_ERROR",
                    error_message=str(exc),
                    processing_run_id=processing_run_id,
                )
                self._idempotency_mgr.fail(
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    error_code="TX_B_ERROR",
                    terminal=False,
                )
                quality = _build_quality_payload(records)
                return asdict(
                    PipelineFailureResult(
                        entry_id=entry_id,
                        user_id=user_id,
                        created_at_utc=_iso_z(ctx.time.created_at_utc),
                        processing_started_at_utc=_iso_z(ctx.time.processing_started_at_utc),
                        processing_completed_at_utc=_iso_z(ctx.time.processing_started_at_utc),
                        local_event_date=ctx.time.local_event_date,
                        error_code="TX_B_ERROR",
                        error_message=str(exc),
                        step="step_16_tx_b",
                        terminal_error={
                            "code": "TX_B_ERROR",
                            "message": str(exc),
                            "step": "step_16_tx_b",
                            "retryable": False,
                        },
                        noncritical_errors=ctx.errors,
                        pipeline_version=PIPELINE_VERSION,
                        ruleset_version=RULESET_VERSION,
                        processing_run_id=processing_run_id,
                        job_id=job_id,
                        step_trace=_build_step_trace(records),
                        quality=quality,
                        provenance=_build_provenance_payload(
                            ctx=ctx,
                            quality=quality,
                            insight_result=ctx.insight_result or {},
                            personality_result=ctx.personality_result or {},
                        ),
                    )
                )

            logger.info(
                "[pipeline:tx_b] TX_B_COMMITTED entry=%s job=%s run=%s",
                entry_id,
                job_id,
                processing_run_id,
            )
            records.append(
                _manual_step_record(
                    step_name="step_16_commit_tx_b",
                    output={"entry_id": entry_id, "job_id": job_id, "status": "committed"},
                    critical=True,
                )
            )

            # Mark idempotency claim completed so future replays get cached result.
            self._idempotency_mgr.complete(
                user_id=user_id,
                idempotency_key=idempotency_key,
                entry_id=entry_id,
                job_id=job_id,
                processing_run_id=processing_run_id,
            )

            # ──────────────────────────────────────────────────────────
            # STEP 17 — Post-commit outbox dispatch + result assembly
            # ──────────────────────────────────────────────────────────
            logger.info("[pipeline:step] STEP_17 post_commit_dispatch entry=%s run=%s", entry_id, processing_run_id)
            self._step_17_dispatch_outbox(ctx=ctx)
            records.append(
                _manual_step_record(
                    step_name="step_17_post_commit_dispatch",
                    output={"outbox_event_count": len(ctx.outbox_events)},
                    critical=False,
                )
            )

            total_ms = int((time.perf_counter() - pipeline_start) * 1000)
            result = self._assemble_success_result(
                ctx=ctx,
                entry_id=entry_id,
                job_id=job_id,
                records=records,
                processing_duration_ms=total_ms,
                now_utc_iso=now_utc.isoformat().replace("+00:00", "Z"),
            )

            logger.info(
                "[pipeline:step] PIPELINE_COMPLETE entry=%s job=%s run=%s "
                "duration_ms=%d steps=%d fallbacks=%d errors=%d",
                entry_id,
                job_id,
                processing_run_id,
                total_ms,
                len(records),
                sum(1 for r in records if r.status == "fallback"),
                len(ctx.errors),
            )
            return result

        except Exception as exc:
            total_ms = int((time.perf_counter() - pipeline_start) * 1000)
            logger.exception(
                "[pipeline:fatal] PIPELINE_EXCEPTION run=%s entry=%s: %s",
                processing_run_id,
                tx_ids.get("entry_id") if tx_ids else "not_created",
                exc,
            )
            if tx_ids is not None and ctx is not None:
                orchestrator = TransactionOrchestrator(self.db)
                self._try_mark_failed(
                    orchestrator=orchestrator,
                    job_id=tx_ids.get("job_id", ""),
                    entry_id=tx_ids.get("entry_id", ""),
                    error_code="PIPELINE_EXCEPTION",
                    error_message=str(exc),
                    processing_run_id=processing_run_id,
                )
            self._idempotency_mgr.fail(
                user_id=user_id,
                idempotency_key=idempotency_key,
                error_code="PIPELINE_EXCEPTION",
                terminal=False,
            )
            quality = _build_quality_payload(records)
            return asdict(
                PipelineFailureResult(
                    entry_id=tx_ids.get("entry_id") if tx_ids else None,
                    user_id=user_id,
                    created_at_utc=_iso_z(ctx.time.created_at_utc) if ctx is not None else None,
                    processing_started_at_utc=_iso_z(ctx.time.processing_started_at_utc)
                    if ctx is not None
                    else "",
                    processing_completed_at_utc=_iso_z(ctx.time.processing_started_at_utc)
                    if ctx is not None
                    else "",
                    local_event_date=ctx.time.local_event_date if ctx is not None else None,
                    error_code="PIPELINE_EXCEPTION",
                    error_message=str(exc),
                    step="unknown",
                    terminal_error={
                        "code": "PIPELINE_EXCEPTION",
                        "message": str(exc),
                        "step": "unknown",
                        "retryable": False,
                    },
                    noncritical_errors=(ctx.errors if ctx is not None else []),
                    processing_duration_ms=total_ms,
                    pipeline_version=PIPELINE_VERSION,
                    ruleset_version=RULESET_VERSION,
                    processing_run_id=processing_run_id,
                    job_id=tx_ids.get("job_id") if tx_ids else None,
                    step_trace=_build_step_trace(records),
                    quality=quality,
                    provenance=(
                        _build_provenance_payload(
                            ctx=ctx,
                            quality=quality,
                            insight_result=ctx.insight_result or {},
                            personality_result=ctx.personality_result or {},
                        )
                        if ctx is not None
                        else {
                            "processing_run_id": processing_run_id,
                            "pipeline_version": PIPELINE_VERSION,
                            "ruleset_version": RULESET_VERSION,
                            "quality_codes": list(quality.get("degraded_codes", [])),
                        }
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Steps 1–4 implementations
    # ------------------------------------------------------------------

    def _step_01_validate(
        self,
        *,
        user_id: str,
        content: str,
        idempotency_key: str,
    ) -> None:
        """Step 1 — Validate and normalise the inbound request (Section 13.6.1)."""
        if not user_id or not user_id.strip():
            raise ValueError("VALIDATION_MISSING_USER_ID: user_id must not be empty")
        if content is None:
            raise ValueError("VALIDATION_MISSING_CONTENT: content must not be None")
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("VALIDATION_MISSING_IDEMPOTENCY_KEY: idempotency_key must not be empty")
        if len(content) > 100_000:
            raise ValueError(
                f"VALIDATION_CONTENT_TOO_LONG: content length {len(content)} exceeds 100 000 chars"
            )

    def _step_03_idempotency_check(
        self,
        *,
        user_id: str,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Step 3 — Idempotency reservation and replay decision (Section 13.6.3).

        Delegates to IdempotencyManager.check_and_reserve().

        Returns:
            Replay payload dict if a prior result exists (completed / in-progress /
            terminal failure), or None to continue with a fresh run.
        """
        is_replay, result = self._idempotency_mgr.check_and_reserve(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if is_replay:
            return result
        return None

    # ------------------------------------------------------------------
    # Steps 5–15 — outside any transaction
    # ------------------------------------------------------------------

    def _run_steps_5_to_15(
        self,
        *,
        ctx: PipelineContext,
        content: str,
        records: List[_StepRecord],
    ) -> None:
        """
        Execute all AI/business logic steps outside any DB transaction.

        Each step populates the corresponding field on *ctx*. Non-critical
        failures produce fallback artifacts and continue. Critical failures
        raise immediately (pipeline terminates).
        """
        now_iso = ctx.time.processing_started_at_utc.isoformat().replace("+00:00", "Z") \
            if hasattr(ctx.time.processing_started_at_utc, "isoformat") \
            else str(ctx.time.processing_started_at_utc)

        # ── Step 5 — Structured extraction with fallback object ──────────
        logger.info(
            "[pipeline:step] STEP_05 structured_extraction entry=%s",
            ctx.entry_id,
        )
        ctx.structured_data = _run_step(
            ctx=ctx,
            step_name="step_05_structured_extraction",
            error_code="STEP_05_EXTRACTION_FAILED",
            critical=False,
            fn=lambda: self._step_05_structured_extraction(ctx=ctx, content=content),
            fallback_fn=lambda exc: _fallback_structured_data(
                error_code=f"STEP_05_EXTRACTION_FAILED:{type(exc).__name__}",
                now_iso=now_iso,
            ),
            records=records,
        )

        # ── Step 6 — Safety evaluation and outbox intent planning ────────
        logger.info(
            "[pipeline:step] STEP_06 safety_evaluation entry=%s",
            ctx.entry_id,
        )
        ctx.safety_result = _run_step(
            ctx=ctx,
            step_name="step_06_safety_evaluation",
            error_code="STEP_06_SAFETY_FAILED",
            critical=False,
            fn=lambda: self._step_06_safety_evaluation(ctx=ctx, content=content),
            fallback_fn=lambda exc: _fallback_safety(
                error_code=f"STEP_06_SAFETY_FAILED:{type(exc).__name__}"
            ),
            records=records,
        )

        # ── Step 7 — Forgiveness update planning ─────────────────────────
        logger.info(
            "[pipeline:step] STEP_07 forgiveness_planning entry=%s",
            ctx.entry_id,
        )
        ctx.forgiveness_result = _run_step(
            ctx=ctx,
            step_name="step_07_forgiveness_planning",
            error_code="STEP_07_FORGIVENESS_FAILED",
            critical=False,
            fn=lambda: self._step_07_forgiveness_planning(ctx=ctx),
            fallback_fn=lambda exc: _fallback_forgiveness(
                error_code=f"STEP_07_FORGIVENESS_FAILED:{type(exc).__name__}"
            ),
            records=records,
        )

        # ── Step 8 — Balance strategy detection and variety precompute ───
        logger.info(
            "[pipeline:step] STEP_08 balance_variety entry=%s",
            ctx.entry_id,
        )
        ctx.strategy_result = _run_step(
            ctx=ctx,
            step_name="step_08_balance_variety",
            error_code="STEP_08_BALANCE_FAILED",
            critical=False,
            fn=lambda: self._step_08_balance_variety(ctx=ctx, content=content),
            fallback_fn=lambda exc: _fallback_balance(
                error_code=f"STEP_08_BALANCE_FAILED:{type(exc).__name__}"
            ),
            records=records,
        )
        # variety lives on strategy_result for now (combined step)
        ctx.variety_result = ctx.strategy_result

        # ── Step 9 — Quest matching / progress / completion ──────────────
        logger.info(
            "[pipeline:step] STEP_09 quest_matching entry=%s",
            ctx.entry_id,
        )
        ctx.quest_result = _run_step(
            ctx=ctx,
            step_name="step_09_quest_matching",
            error_code="STEP_09_QUEST_FAILED",
            critical=False,
            fn=lambda: self._step_09_quest_matching(ctx=ctx),
            fallback_fn=lambda exc: _fallback_quest(
                error_code=f"STEP_09_QUEST_FAILED:{type(exc).__name__}"
            ),
            records=records,
        )

        # ── Step 10 — Anomaly scoring and troll multiplier resolution ────
        logger.info(
            "[pipeline:step] STEP_10 anomaly_scoring entry=%s",
            ctx.entry_id,
        )
        ctx.anomaly_result = _run_step(
            ctx=ctx,
            step_name="step_10_anomaly_scoring",
            error_code="STEP_10_ANOMALY_FAILED",
            critical=False,
            fn=lambda: self._step_10_anomaly_scoring(ctx=ctx),
            fallback_fn=lambda exc: _fallback_anomaly(
                error_code=f"STEP_10_ANOMALY_FAILED:{type(exc).__name__}"
            ),
            records=records,
        )

        # ── Step 11 — Harmony refresh planning ───────────────────────────
        logger.info(
            "[pipeline:step] STEP_11 harmony_refresh entry=%s",
            ctx.entry_id,
        )
        ctx.harmony_result = _run_step(
            ctx=ctx,
            step_name="step_11_harmony_refresh",
            error_code="STEP_11_HARMONY_FAILED",
            critical=False,
            fn=lambda: self._step_11_harmony_refresh(ctx=ctx),
            fallback_fn=lambda exc: _fallback_harmony(
                error_code=f"STEP_11_HARMONY_FAILED:{type(exc).__name__}"
            ),
            records=records,
        )

        # ── Step 12 — Insight discovery planning ─────────────────────────
        logger.info(
            "[pipeline:step] STEP_12 insight_discovery entry=%s",
            ctx.entry_id,
        )
        ctx.insight_result = _run_step(
            ctx=ctx,
            step_name="step_12_insight_discovery",
            error_code="STEP_12_INSIGHT_FAILED",
            critical=False,
            fn=lambda: self._step_12_insight_discovery(ctx=ctx, content=content),
            fallback_fn=lambda exc: _fallback_insight(
                user_id=ctx.user_id,
                entry_id=ctx.entry_id,
                error_code=f"STEP_12_INSIGHT_FAILED:{type(exc).__name__}",
            ),
            records=records,
        )

        # ── Step 13 — Story arc snapshot + progression planning ──────────
        logger.info(
            "[pipeline:step] STEP_13 arc_progression entry=%s",
            ctx.entry_id,
        )
        ctx.arc_result = _run_step(
            ctx=ctx,
            step_name="step_13_arc_progression",
            error_code="STEP_13_ARC_FAILED",
            critical=False,
            fn=lambda: self._step_13_arc_progression(ctx=ctx),
            fallback_fn=lambda exc: _fallback_arc(
                error_code=f"STEP_13_ARC_FAILED:{type(exc).__name__}"
            ),
            records=records,
        )

        # ── Step 14 — Final XP/level/skill/theme computation (CRITICAL) ──
        logger.info(
            "[pipeline:step] STEP_14 xp_computation entry=%s",
            ctx.entry_id,
        )
        ctx.xp_result = _run_step(
            ctx=ctx,
            step_name="step_14_xp_computation",
            error_code="STEP_14_XP_COMPUTATION_FAILED",
            critical=True,   # XP formula failure terminates the pipeline
            fn=lambda: self._step_14_xp_computation(ctx=ctx),
            fallback_fn=None,
            records=records,
        )

        # ── Step 15 — Personality selection and message generation ────────
        logger.info(
            "[pipeline:step] STEP_15 personality_message entry=%s",
            ctx.entry_id,
        )
        ctx.personality_result = _run_step(
            ctx=ctx,
            step_name="step_15_personality_message",
            error_code="STEP_15_PERSONALITY_FAILED",
            critical=False,
            fn=lambda: self._step_15_personality_message(ctx=ctx, content=content),
            fallback_fn=lambda exc: _fallback_personality(
                error_code=f"STEP_15_PERSONALITY_FAILED:{type(exc).__name__}"
            ),
            records=records,
        )

        # ── Step 15b — System report (deterministic, no LLM) ─────────────
        logger.info(
            "[pipeline:step] STEP_15B system_report entry=%s",
            ctx.entry_id,
        )
        ctx.report_result = _run_step(
            ctx=ctx,
            step_name="step_15b_system_report",
            error_code="STEP_15B_REPORT_FAILED",
            critical=False,
            fn=lambda: self._step_15b_system_report(ctx=ctx),
            fallback_fn=lambda exc: _fallback_system_report(
                error_code=f"STEP_15B_REPORT_FAILED:{type(exc).__name__}"
            ),
            records=records,
        )

    # ------------------------------------------------------------------
    # Individual step implementations
    # ------------------------------------------------------------------

    def _step_05_structured_extraction(
        self, *, ctx: PipelineContext, content: str
    ) -> Dict[str, Any]:
        """
        Step 5 — Structured extraction with fallback object.

        Uses rule-based signal detection from src.ai.steps.signals +
        structured field mapping. LLM call (Ollama) is attempted when
        available; if unavailable the rule-based path is used exclusively.
        """
        from src.ai.steps import normalize as _s_normalize
        from src.ai.steps import signals as _s_signals
        from src.db.base import SessionLocal

        now_iso = _iso_z(ctx.time.processing_started_at_utc)

        with SessionLocal() as db:
            normalized = _s_normalize.run(content)
            logger.debug(
                "[pipeline:step] extraction_normalized entry=%s words=%d chars=%d",
                ctx.entry_id,
                normalized["word_count"],
                normalized["char_count"],
            )
            detection = _s_signals.run(
                user_id=ctx.user_id,
                canonical_text=normalized["canonical_text"],
                db=db,
                ollama_health=getattr(self, "ollama_health", None),
                ollama=getattr(self, "ollama", None),
                rag_hits=[],
                qdrant=getattr(self, "qdrant", None),
            )
            logger.debug(
                "[pipeline:step] extraction_detection entry=%s skills=%s activities=%s",
                ctx.entry_id,
                detection.get("detected_skills"),
                detection.get("detected_activities"),
            )
            resolution = resolve_entry_skill_signals(
                user_id=ctx.user_id,
                canonical_text=normalized["canonical_text"],
                detected_skills=detection.get("detected_skills", []),
                detected_activities=detection.get("detected_activities", []),
                detected_global_skill_ids=detection.get("detected_global_skills", []),
                detected_skill_weights=detection.get("skills_weights", {}),
                detected_global_skill_weights=detection.get("global_skills_weights", {}),
                db=db,
            )

        # Map detection → structured schema
        return {
            "canonical_text": normalized["canonical_text"],
            "char_count": normalized["char_count"],
            "word_count": normalized["word_count"],
            "primary_action_type": (
                detection["detected_activities"][0]
                if detection["detected_activities"]
                else None
            ),
            "dominant_emotions": detection["dominant_emotions"],
            "energy_level": detection["energy_level"],
            "self_compassion_score": detection["self_compassion_score"],
            "task_type": detection["task_type"],
            "skills_themes_involved": (
                resolution.resolved_skill_names or detection["detected_skills"]
            ),
            "safety_flags": detection.get("safety_flags", []),
            "source_skills_weights_bp": resolution.source_skills_weights_bp,
            "skills_weights_bp": resolution.skills_weights_bp,
            "resolved_skill_names": resolution.resolved_skill_names,
            "extraction_confidence_score": resolution.extraction_confidence_score,
            "pattern_hits_json": resolution.pattern_hits_json,
            "extraction_status": "succeeded",
            "extracted_at": now_iso,
            "fallback_used": False,
        }

    def _step_06_safety_evaluation(
        self, *, ctx: PipelineContext, content: str
    ) -> Dict[str, Any]:
        """
        Step 6 — Safety evaluation (Section 13.6.6).

        Derives safety classification from structured extraction output.
        If structured_data is unavailable (fallback), derives from raw content.
        Queues safety outbox events when risk_level != 'none'.
        """
        sd = ctx.structured_data or {}
        energy: int = int(sd.get("energy_level") or 5)
        compassion: int = int(sd.get("self_compassion_score") or 7)
        emotions: List[str] = [str(e).lower() for e in sd.get("dominant_emotions") or []]
        safety_flags: List[str] = sd.get("safety_flags") or []

        _NEGATIVE = {"sad", "anxious", "angry", "depressed", "stressed", "hopeless"}
        is_negative = any(e in _NEGATIVE for e in emotions)

        force_therapist = energy < 3 and is_negative
        if energy < 2:
            risk_level = "crisis"
        elif energy < 4 and is_negative:
            risk_level = "warning"
        else:
            risk_level = "none"

        sentiment_score = int((energy / 10.0) * 50 + (compassion / 10.0) * 50)

        result = {
            "risk_level": risk_level,
            "force_therapist": force_therapist,
            "sentiment_score": sentiment_score,
            "safety_flags": safety_flags,
            "fallback_used": False,
        }

        if risk_level != "none":
            ctx.queue_outbox_event(
                "safety.alert",
                {
                    "entry_id": ctx.entry_id,
                    "user_id": ctx.user_id,
                    "risk_level": risk_level,
                    "force_therapist": force_therapist,
                },
            )
            logger.warning(
                "[pipeline:step] SAFETY_ALERT entry=%s risk_level=%s force_therapist=%s",
                ctx.entry_id,
                risk_level,
                force_therapist,
            )

        return result

    def _step_07_forgiveness_planning(self, *, ctx: PipelineContext) -> Dict[str, Any]:
        """
        Step 7 — Forgiveness / decay update planning (Section 13.6.7).

        Reads the user's forgiveness config and computes whether staleness
        should be reset for affected skills.
        """
        try:
            from src.core.forgiveness_decay_service import ForgivenessDecayService
            from src.db.base import SessionLocal

            with SessionLocal() as db:
                svc = ForgivenessDecayService(db)
                config = svc.get_config_for_user(ctx.user_id)
                return {
                    "preset": config.preset if config else "balanced",
                    "skill_decay_rate": float(config.skill_decay_rate) if config else 0.1,
                    "grace_period_days": int(config.skill_grace_period_days) if config else 3,
                    "updates_applied": 0,  # actual reset done in Tx B
                    "fallback_used": False,
                }
        except Exception as exc:
            logger.warning(
                "[pipeline:error] forgiveness_config_load failed entry=%s: %s",
                ctx.entry_id,
                exc,
            )
            return {
                "preset": "balanced",
                "skill_decay_rate": 0.1,
                "grace_period_days": 3,
                "updates_applied": 0,
                "fallback_used": False,
            }

    def _step_08_balance_variety(
        self, *, ctx: PipelineContext, content: str
    ) -> Dict[str, Any]:
        """
        Step 8 — Balance strategy detection and variety precompute (Section 13.6.8).

        Runs strategy detector and variety scorer. Results feed into the XP
        computation step as multipliers.
        """
        from src.ai.steps import strategy as _s_strategy
        from src.ai.steps import variety as _s_variety
        from src.db.base import SessionLocal

        sd = ctx.structured_data or {}
        detection = {
            "detected_skills": sd.get("skills_themes_involved", []),
            "detected_activities": (
                [sd["primary_action_type"]] if sd.get("primary_action_type") else []
            ),
        }

        with SessionLocal() as db:
            strategy_out = _s_strategy.run(
                user_id=ctx.user_id,
                entry_id=ctx.entry_id,
                canonical_text=sd.get("canonical_text", content),
                detection=detection,
                anomaly_score=0.0,  # anomaly not computed yet at step 8
                db=db,
            )
            variety_out = _s_variety.run(user_id=ctx.user_id, db=db)

        logger.debug(
            "[pipeline:step] balance_variety entry=%s strategies=%s variety_score=%.3f "
            "variety_multiplier_bp=%d diminishing_bp=%d",
            ctx.entry_id,
            strategy_out.get("detected_strategies"),
            variety_out.get("variety_score", 0.0),
            variety_out.get("variety_multiplier_bp", 10000),
            strategy_out.get("diminishing_bp", 10000),
        )

        return {
            **strategy_out,
            **variety_out,
            "fallback_used": False,
        }

    def _step_09_quest_matching(self, *, ctx: PipelineContext) -> Dict[str, Any]:
        """
        Step 9 — Quest matching, progress, completion candidate resolution
        and failure penalty resolution (Section 13.6.9).

        Uses the v2 QuestMatcherStep when available, falls back to the
        legacy match+update_progress path.
        """
        from src.ai.pipeline_steps.quest_matcher_step import QuestMatcherStep
        from src.db.base import SessionLocal
        from src.db.models.journal_entry import JournalEntry
        from src.db.models.user import User

        with SessionLocal() as db:
            user = db.query(User).filter(User.id == ctx.user_id).one_or_none()
            entry = (
                db.query(JournalEntry)
                .filter(
                    JournalEntry.id == ctx.entry_id,
                    JournalEntry.user_id == ctx.user_id,
                )
                .one_or_none()
            )
            if user is None or entry is None:
                logger.warning(
                    "[pipeline:step] quest_matching skipped — user/entry not found entry=%s",
                    ctx.entry_id,
                )
                return _fallback_quest("STEP_09_USER_OR_ENTRY_NOT_FOUND")

            structured_data = ctx.structured_data or {}
            troll_bp = (ctx.anomaly_result or {}).get("troll_bp", 10000)
            variety_bp = (ctx.strategy_result or {}).get("variety_multiplier_bp", 10000)

            logger.debug(
                "[pipeline:step] quest_matching entry=%s troll_bp=%d variety_bp=%d",
                ctx.entry_id,
                troll_bp,
                variety_bp,
            )

            step = QuestMatcherStep(db)
            result = step.execute(
                user=user,
                entry=entry,
                structured_data=structured_data,
                troll_multiplier_bp=troll_bp,
                variety_multiplier_bp=variety_bp,
                processing_run_id=ctx.processing_run_id,
            )

        instant = result.get("instant_quest")
        streak_quests = result.get("streak_quests", [])
        xp_awards = result.get("xp_awards", [])
        created_quests = result.get("created_quests", [])
        progressed_quests = result.get("progressed_quests", [])
        completed_quests = result.get("completed_quests", [])

        serialized = {
            "instant_quest_id": instant.id if instant is not None else None,
            "streak_quest_ids": [q.id for q in streak_quests],
            "created_quests": [_serialize_quest(q) for q in created_quests],
            "progressed_quests": [_serialize_quest(q) for q in progressed_quests],
            "completed_quests": [_serialize_quest(q) for q in completed_quests],
            "xp_awards": [_serialize_xp_award(a) for a in xp_awards],
            "xp_award_count": len(xp_awards),
            "total_xp_awarded": result.get("total_xp_awarded", 0),
            "failure_penalty_xp": result.get("failure_penalty_xp", 0),
            "notes": result.get("notes", []),
            "fallback_used": False,
        }
        logger.debug(
            "[pipeline:step] quest_matching_done entry=%s created=%d completed=%d "
            "progressed=%d xp_awards=%d total_xp=%d",
            ctx.entry_id,
            len(created_quests),
            len(completed_quests),
            len(progressed_quests),
            len(xp_awards),
            serialized["total_xp_awarded"],
        )
        return serialized

    def _step_10_anomaly_scoring(self, *, ctx: PipelineContext) -> Dict[str, Any]:
        """
        Step 10 — Anomaly scoring and troll multiplier resolution (Section 13.6.10).

        Runs AnomalyOrchestrator.ensure_anomaly_score to derive the troll
        multiplier that gates XP at step 14.
        """
        from decimal import Decimal
        from src.core.anomaly_orchestrator import AnomalyOrchestrator
        from src.db.base import SessionLocal

        now_utc = ctx.time.processing_started_at_utc
        if not isinstance(now_utc, datetime):
            now_utc = datetime.fromisoformat(str(now_utc).replace("Z", "+00:00"))

        with SessionLocal() as db:
            result = AnomalyOrchestrator(db).ensure_anomaly_score(
                user_id=ctx.user_id,
                entry_id=ctx.entry_id,
                now_utc=now_utc,
            )

        troll_m = Decimal(str(result["troll_multiplier"])).quantize(Decimal("0.000001"))
        troll_bp = int(troll_m * Decimal("10000"))
        components = result["detection_factors"].get("components", [])

        logger.debug(
            "[pipeline:step] anomaly_scoring entry=%s score=%.2f troll_multiplier=%.4f troll_bp=%d",
            ctx.entry_id,
            float(result["score"]),
            float(troll_m),
            troll_bp,
        )

        return {
            "anomaly_score": float(result["score"]),
            "score": float(result["score"]),
            "troll_multiplier": float(troll_m),
            "troll_bp": troll_bp,
            "detection_factors": result["detection_factors"],
            "reasons": [c.get("key", "") for c in components if c.get("key")],
            "calculated_at": result["calculated_at"],
            "fallback_used": False,
        }

    def _step_11_harmony_refresh(self, *, ctx: PipelineContext) -> Dict[str, Any]:
        """
        Step 11 — Harmony refresh planning with frozen local date semantics
        (Section 13.6.11).

        Classifies harmony dimensions from structured data and computes a
        refreshed harmony snapshot. Actual DB write happens in Tx B.
        """
        from src.core.harmony_classifier import HarmonyClassifier
        from src.core.harmony_refresh_service import HarmonyRefreshService
        from src.db.base import SessionLocal
        from src.db.models.journal_entry import JournalEntry, JournalEntryStructured

        now_utc = ctx.time.processing_started_at_utc
        if not isinstance(now_utc, datetime):
            now_utc = datetime.fromisoformat(str(now_utc).replace("Z", "+00:00"))

        with SessionLocal() as db:
            entry = (
                db.query(JournalEntry)
                .filter(
                    JournalEntry.id == ctx.entry_id,
                    JournalEntry.user_id == ctx.user_id,
                )
                .one_or_none()
            )
            structured_orm = (
                db.query(JournalEntryStructured)
                .filter(
                    JournalEntryStructured.user_id == ctx.user_id,
                    JournalEntryStructured.entry_id == ctx.entry_id,
                )
                .one_or_none()
            )

            dims: set = set()
            if entry is not None and structured_orm is not None:
                dims = HarmonyClassifier(db).classify_dimensions(entry, structured_orm)

            result = HarmonyRefreshService(db).refresh_harmony(
                user_id=ctx.user_id,
                now_utc=now_utc,
                advance_overwork_state=True,
            )

        logger.debug(
            "[pipeline:step] harmony_refresh entry=%s dims=%s overall_balance=%.3f overwork=%d",
            ctx.entry_id,
            sorted(dims),
            float(result.harmony.overall_balance or 0.5),
            int(result.harmony.overwork_stage or 0),
        )

        return {
            "dimensions_addressed": sorted(dims),
            "overall_balance": float(result.harmony.overall_balance or 0.5),
            "overwork_stage": int(result.harmony.overwork_stage or 0),
            "fallback_used": False,
        }

    def _step_12_insight_discovery(
        self, *, ctx: PipelineContext, content: str
    ) -> Dict[str, Any]:
        """
        Step 12 — Insight discovery planning (Section 13.6.12).

        Generates an LLM-backed insight grounded in RAG retrieval.
        LLM + RAG calls both logged with appropriate namespaces.
        """
        from src.ai.steps import embedding as _s_embedding
        from src.ai.steps import rag as _s_rag
        from src.ai.steps import insights as _s_insights

        sd = ctx.structured_data or {}
        canonical_text = sd.get("canonical_text", content)
        detection = {
            "detected_skills": sd.get("skills_themes_involved", []),
            "detected_activities": (
                [sd["primary_action_type"]] if sd.get("primary_action_type") else []
            ),
            "task_type": sd.get("task_type", "unknown"),
        }

        # Health check for Ollama
        ollama_health: Dict[str, Any] = {"connected": False, "model_available": False, "models": []}
        if self.ollama is not None:
            try:
                ollama_health = self.ollama.health()
                logger.debug(
                    "[pipeline:llm] ollama_health_check entry=%s connected=%s model_available=%s",
                    ctx.entry_id,
                    ollama_health.get("connected"),
                    ollama_health.get("model_available"),
                )
            except Exception as exc:
                logger.warning(
                    "[pipeline:llm] ollama_health_check_failed entry=%s: %s",
                    ctx.entry_id,
                    exc,
                )

        # Embedding → RAG retrieval
        rag_hits: List[Dict[str, Any]] = []
        if self.ollama is not None:
            try:
                embedding = _s_embedding.run(
                    entry_id=ctx.entry_id,
                    normalized_text=canonical_text,
                    ollama_health=ollama_health,
                    ollama=self.ollama,
                    qdrant=self.qdrant,
                    cache=self.cache,
                )
                vector = embedding.get("vector", [])
                logger.debug(
                    "[pipeline:rag] embedding_generated entry=%s vector_dim=%d from_cache=%s",
                    ctx.entry_id,
                    len(vector),
                    embedding.get("from_cache"),
                )
                if vector and self.qdrant is not None:
                    rag_result = _s_rag.run(
                        vector=vector,
                        qdrant=self.qdrant,
                        cache=self.cache,
                        entry_id=ctx.entry_id,
                    )
                    rag_hits = rag_result.get("hits", [])
                    logger.debug(
                        "[pipeline:rag] rag_search_done entry=%s hits=%d",
                        ctx.entry_id,
                        len(rag_hits),
                    )
            except Exception as exc:
                logger.warning(
                    "[pipeline:rag] rag_retrieval_failed entry=%s: %s",
                    ctx.entry_id,
                    exc,
                )

        logger.debug(
            "[pipeline:llm] insight_llm_call entry=%s ollama_connected=%s rag_hits=%d",
            ctx.entry_id,
            ollama_health.get("connected"),
            len(rag_hits),
        )

        from src.db.base import SessionLocal

        with SessionLocal() as db:
            plan = _s_insights.plan(
                user_id=ctx.user_id,
                entry_id=ctx.entry_id,
                canonical_text=canonical_text,
                rag_hits=rag_hits,
                detection=detection,
                ollama_health=ollama_health,
                ollama=self.ollama,
                db=db,
                cache=self.cache,
            )

        logger.debug(
            "[pipeline:llm] insight_plan_done entry=%s from_ollama=%s from_cache=%s "
            "confidence=%.2f",
            ctx.entry_id,
            plan.get("from_ollama"),
            plan.get("from_cache"),
            plan.get("insight_confidence", 0.0),
        )

        return {
            **plan,
            "rag_hits": rag_hits,
            "rag_hit_count": len(rag_hits),
            "ollama_connected": ollama_health.get("connected", False),
            "fallback_used": not plan.get("from_ollama", False),
        }

    def _step_13_arc_progression(self, *, ctx: PipelineContext) -> Dict[str, Any]:
        """
        Step 13 — Story arc snapshot, progression planning, and arc multiplier
        source resolution (Section 13.6.13).
        """
        from src.core.arc_lifecycle import ArcLifecycleService
        from src.core.arc_recovery_detection import RecoveryDetectionService
        from src.core.arc_regression_trigger import RegressionTriggerService
        from src.core.arc_vacation import VacationModeService
        from src.db.base import SessionLocal
        from src.db.models.journal_entry import JournalEntry
        from src.db.models.user import User

        def _arc_summary(arc: Any) -> Dict[str, Any]:
            return {
                "arc_id": arc.id,
                "arc_type": arc.arc_type,
                "status": arc.status,
                "event_name": getattr(arc, "event_name", None),
            }

        with SessionLocal() as db:
            user = db.query(User).filter(User.id == ctx.user_id).one_or_none()
            entry = (
                db.query(JournalEntry)
                .filter(
                    JournalEntry.id == ctx.entry_id,
                    JournalEntry.user_id == ctx.user_id,
                )
                .one_or_none()
            )
            if user is None:
                return _fallback_arc("STEP_13_USER_NOT_FOUND")

            lifecycle = ArcLifecycleService(db)
            vacation_svc = VacationModeService(db)
            regression_svc = RegressionTriggerService(db)
            recovery_svc = RecoveryDetectionService(db)

            updates: List[Dict[str, Any]] = []
            notes: List[str] = []

            active_arc = lifecycle.reconcile_active_arc_cache(user.id)
            cached_id = user.active_arc_id
            if cached_id != (active_arc.id if active_arc else None):
                updates.append({
                    "action": "cache_repaired",
                    "cached_arc_id": cached_id,
                    "active_arc_id": active_arc.id if active_arc else None,
                })

            # Auto-expire event arcs that have exceeded their duration
            if (
                active_arc is not None
                and active_arc.arc_type == "event"
                and active_arc.duration_days is not None
                and lifecycle.calculate_days_active(active_arc) >= float(active_arc.duration_days)
            ):
                if active_arc.event_name == "vacation_mode":
                    ended, resumed = vacation_svc.end_vacation(user.id)
                    updates.append({"action": "auto_expired", "arc": _arc_summary(ended)})
                    if resumed:
                        updates.append({"action": "resumed", "arc": _arc_summary(resumed)})
                else:
                    expired = lifecycle.complete_arc(
                        arc=active_arc,
                        trigger_type="auto_expiry",
                        trigger_data={"entry_id": ctx.entry_id},
                    )
                    updates.append({"action": "auto_expired", "arc": _arc_summary(expired)})
                active_arc = lifecycle.reconcile_active_arc_cache(user.id)

            # Regression / redemption transitions
            if active_arc is not None and active_arc.arc_type == "regression":
                prior_id = active_arc.id
                redemption = recovery_svc.check_and_transition_to_redemption(user.id)
                active_arc = lifecycle.reconcile_active_arc_cache(user.id)
                if redemption is not None:
                    updates.append({
                        "action": "transitioned_to_redemption",
                        "from_arc_id": prior_id,
                        "arc": _arc_summary(redemption),
                    })
            else:
                regression = regression_svc.check_and_trigger_regression(user.id)
                active_arc = lifecycle.reconcile_active_arc_cache(user.id)
                if regression is not None:
                    updates.append({"action": "regression_triggered", "arc": _arc_summary(regression)})
                elif active_arc is not None and active_arc.arc_type == "event":
                    notes.append("REGRESSION_CHECK_DEFERRED")

            db.flush()

        arc_multiplier = 1.0
        if active_arc is not None and hasattr(active_arc, "arc_multiplier"):
            arc_multiplier = float(getattr(active_arc, "arc_multiplier") or 1.0)
        arc_multiplier_bp = int(arc_multiplier * 10000)

        logger.debug(
            "[pipeline:step] arc_progression entry=%s active_arc=%s arc_multiplier=%.2f updates=%d",
            ctx.entry_id,
            active_arc.id if active_arc else None,
            arc_multiplier,
            len(updates),
        )

        return {
            "active_arc": _arc_summary(active_arc) if active_arc else None,
            "arc_updates": updates,
            "arc_multiplier": arc_multiplier,
            "arc_multiplier_bp": arc_multiplier_bp,
            "notes": notes,
            "fallback_used": False,
        }

    def _step_14_xp_computation(self, *, ctx: PipelineContext) -> Dict[str, Any]:
        """
        Step 14 — Final XP / level / skill / theme computation (CRITICAL).

        Calls the canonical XP formula with all gathered multipliers.
        A failure here is terminal — the pipeline cannot continue without XP.
        """
        from src.ai.steps import rewards as _s_rewards
        from src.ai.steps import progression as _s_progression
        from src.db.base import SessionLocal

        quest_result = ctx.quest_result or {}
        completed_quests = quest_result.get("completed_quests", [])
        variety_bp = (ctx.strategy_result or {}).get("variety_multiplier_bp", 10000)
        troll_bp = (ctx.anomaly_result or {}).get("troll_bp", 10000)
        diminishing_bp = (ctx.strategy_result or {}).get("diminishing_bp", 10000)
        arc_bp = (ctx.arc_result or {}).get("arc_multiplier_bp", 10000)

        logger.debug(
            "[pipeline:step] xp_computation entry=%s quest_count=%d variety_bp=%d "
            "troll_bp=%d diminishing_bp=%d arc_bp=%d",
            ctx.entry_id,
            len(completed_quests),
            variety_bp,
            troll_bp,
            diminishing_bp,
            arc_bp,
        )

        # Build quest payloads from completed_quests serialised dicts
        completed_payloads = [
            {
                "quest_id": q.get("quest_id", q.get("id", "")),
                "skill_id": q.get("skill_id"),
                "base_xp": q.get("base_xp", 480),
            }
            for q in completed_quests
        ]

        rewards = _s_rewards.compute_quest_rewards(
            completed_quests=completed_payloads,
            variety_multiplier_bp=variety_bp,
            troll_bp=troll_bp,
            diminishing_bp=diminishing_bp,
        )

        with SessionLocal() as db:
            skill_awards = _s_rewards.persist_skill_awards(
                user_id=ctx.user_id,
                entry_id=ctx.entry_id,
                processing_run_id=ctx.processing_run_id,
                rewards=rewards["rewards"],
                db=db,
                pipeline_version=PIPELINE_VERSION,
                ruleset_version=RULESET_VERSION,
            )
            theme_awards = _s_rewards.persist_theme_awards(
                user_id=ctx.user_id,
                entry_id=ctx.entry_id,
                processing_run_id=ctx.processing_run_id,
                skill_awards=skill_awards["skill_awards"],
                db=db,
                pipeline_version=PIPELINE_VERSION,
                ruleset_version=RULESET_VERSION,
            )
            progression = _s_progression.update_counters(
                skill_awards=skill_awards["skill_awards"],
                theme_awards=theme_awards["theme_awards"],
                db=db,
                user_id=ctx.user_id,
                entry_id=ctx.entry_id,
            )
            db.commit()

        all_awards = list(skill_awards["skill_awards"]) + list(theme_awards["theme_awards"])
        total_xp = sum(int(a.get("amount", 0)) for a in all_awards)

        logger.debug(
            "[pipeline:step] xp_computation_done entry=%s awards=%d total_xp=%d "
            "updated_skills=%d updated_themes=%d",
            ctx.entry_id,
            len(all_awards),
            total_xp,
            progression.get("updated_skills", 0),
            progression.get("updated_themes", 0),
        )

        return {
            "rewards": rewards["rewards"],
            "skill_awards": skill_awards["skill_awards"],
            "theme_awards": theme_awards["theme_awards"],
            "awards": all_awards,
            "total_xp": total_xp,
            "updated_skills": progression.get("updated_skills", 0),
            "updated_themes": progression.get("updated_themes", 0),
            "progression": progression,
            "variety_bp": variety_bp,
            "troll_bp": troll_bp,
            "diminishing_bp": diminishing_bp,
            "arc_bp": arc_bp,
            "fallback_used": False,
        }

    def _step_15_personality_message(
        self, *, ctx: PipelineContext, content: str
    ) -> Dict[str, Any]:
        """
        Step 15 — Personality selection and message generation planning
        (Section 13.6.15).

        Calls PersonalityOrchestrator which handles LLM + RAG internally.
        Falls back to neutral observer message on any failure.
        """
        from src.core.personality_orchestrator import PersonalityOrchestrator
        from src.db.base import SessionLocal

        safety_result = ctx.safety_result or {}
        harmony = ctx.harmony_result or {}
        anomaly = ctx.anomaly_result or {}
        arc = ctx.arc_result or {}
        quest = ctx.quest_result or {}

        now_utc = ctx.time.processing_started_at_utc
        if not isinstance(now_utc, datetime):
            now_utc = datetime.fromisoformat(str(now_utc).replace("Z", "+00:00"))

        user_state = {
            "harmony_score": int(float(harmony.get("overall_balance", 0.5)) * 100),
            "anomaly_score": anomaly.get("anomaly_score", 0.0),
            "anomaly_contribution": anomaly.get("anomaly_score", 0.0),
            "tutorial_active": bool(
                arc.get("active_arc") and arc["active_arc"].get("arc_type") == "tutorial"
            ),
            "regression_arc_active": bool(
                arc.get("active_arc") and arc["active_arc"].get("arc_type") == "regression"
            ),
            "major_achievement": bool(quest.get("completed_quests")),
            "skills": (ctx.structured_data or {}).get("skills_themes_involved", []),
            "overwork_stage": harmony.get("overwork_stage", 0),
        }

        logger.debug(
            "[pipeline:llm] personality_selection entry=%s force_therapist=%s "
            "risk_level=%s harmony_score=%d major_achievement=%s",
            ctx.entry_id,
            safety_result.get("force_therapist"),
            safety_result.get("risk_level"),
            user_state["harmony_score"],
            user_state["major_achievement"],
        )

        with SessionLocal() as db:
            plan = PersonalityOrchestrator(db).plan_entry_personality(
                user_id=ctx.user_id,
                entry_id=ctx.entry_id,
                entry_text=content,
                user_state=user_state,
                safety_result=safety_result,
                requested_personality=None,
                now_utc=now_utc,
                pipeline_version=PIPELINE_VERSION,
            )

        logger.debug(
            "[pipeline:llm] personality_plan_done entry=%s personality=%s "
            "message_type=%s selection_reason=%s",
            ctx.entry_id,
            plan.get("personality"),
            plan.get("message_type"),
            plan.get("selection_reason"),
        )

        return {
            **plan,
            "fallback_used": False,
        }

    # ------------------------------------------------------------------
    # Step 15b — System report generation
    # ------------------------------------------------------------------

    def _step_15b_system_report(self, *, ctx: PipelineContext) -> Dict[str, Any]:
        """
        Step 15b — Deterministic system report for the chat panel.

        Reads all accumulated step results from *ctx* and assembles a
        human-readable plain-text report plus a machine-readable context_data
        dict. No LLM calls, no DB writes — all data is already on ctx.
        Persisted as a PersonalityMessage(personality='system') in Tx B.
        """
        from datetime import timezone as _tz

        xp = ctx.xp_result or {}
        quest = ctx.quest_result or {}
        anomaly = ctx.anomaly_result or {}
        variety = ctx.variety_result or {}
        strategy = ctx.strategy_result or {}
        structured = ctx.structured_data or {}

        # Approximate processing duration from pipeline start timestamp
        now_utc = datetime.now(_tz.utc)
        started = ctx.time.processing_started_at_utc
        if started.tzinfo is None:
            started = started.replace(tzinfo=_tz.utc)
        approx_ms = int((now_utc - started).total_seconds() * 1000)

        lines: List[str] = [
            f"SYSTEM REPORT — {ctx.time.local_event_date}",
            f"Processing: ~{approx_ms} ms",
        ]

        # Skills detected
        skills = structured.get("resolved_skill_names", [])
        if skills:
            lines.append(f"\n--- SKILLS ---\n  {', '.join(skills)}")

        # Emotions / energy
        emotions = structured.get("dominant_emotions", [])
        energy = structured.get("energy_level")
        if emotions or energy is not None:
            parts = []
            if emotions:
                parts.append(f"emotions: {', '.join(str(e) for e in emotions)}")
            if energy is not None:
                parts.append(f"energy: {energy}")
            lines.append(f"\n--- SIGNALS ---\n  {' | '.join(parts)}")

        # XP awards
        skill_awards = xp.get("skill_awards", [])
        theme_awards = xp.get("theme_awards", [])
        all_awards = skill_awards + theme_awards
        if all_awards:
            lines.append("\n--- XP GAINS ---")
            for award in all_awards:
                name = award.get("skill_name") or award.get("theme_name", "?")
                amt = award.get("amount", 0)
                lines.append(f"  {name}: +{amt} XP")
            total_xp = xp.get("total_xp", 0)
            lines.append(f"  ──────────────\n  Total: +{total_xp} XP")

        # Multipliers (only show non-neutral ones)
        troll_bp = anomaly.get("troll_multiplier_bp", 10000)
        variety_bp = variety.get("variety_multiplier_bp", 10000)
        dim_bp = strategy.get("diminishing_bp", 10000)
        if any(x != 10000 for x in [troll_bp, variety_bp, dim_bp]):
            lines.append("\n--- MULTIPLIERS ---")
            if troll_bp != 10000:
                lines.append(f"  Troll:       {troll_bp / 10000:.2f}x")
            if variety_bp != 10000:
                lines.append(f"  Variety:     {variety_bp / 10000:.2f}x")
            if dim_bp != 10000:
                lines.append(f"  Diminishing: {dim_bp / 10000:.2f}x")

        # Quests
        completed_quests = quest.get("completed_quests", [])
        progressed_quests = quest.get("progressed_quests", [])
        if completed_quests or progressed_quests:
            lines.append("\n--- QUESTS ---")
            for q in completed_quests:
                title = q.get("title") or q.get("quest_id", "?")
                lines.append(f"  COMPLETED:  {title}")
            for q in progressed_quests:
                title = q.get("title") or q.get("quest_id", "?")
                prog = q.get("progress_value")
                req = q.get("required_progress")
                suffix = f" ({prog}/{req})" if prog is not None and req is not None else ""
                lines.append(f"  Progressed: {title}{suffix}")

        # Strategies
        detected_strategies = strategy.get("detected_strategies", [])
        if detected_strategies:
            lines.append(f"\n--- STRATEGY ---\n  {', '.join(detected_strategies)}")

        message_text = "\n".join(lines)

        context_data: Dict[str, Any] = {
            "pipeline_version": PIPELINE_VERSION,
            "approx_processing_ms": approx_ms,
            "xp_result": xp,
            "quest_result": quest,
            "anomaly_result": anomaly,
            "variety_result": variety,
            "strategy_result": strategy,
            "structured_data": {
                "resolved_skill_names": skills,
                "dominant_emotions": emotions,
                "energy_level": energy,
            },
        }

        logger.debug(
            "[pipeline:step] system_report built entry=%s skills=%d awards=%d",
            ctx.entry_id,
            len(skills),
            len(all_awards),
        )

        return {
            "personality": "system",
            "message_type": "report_summary",
            "message_text": message_text,
            "logical_slot_key": "system_report",
            "selector_version": 1,
            "context_data": context_data,
            "fallback_used": False,
        }

    # ------------------------------------------------------------------
    # Step 17 — Post-commit outbox dispatch
    # ------------------------------------------------------------------

    def _step_17_dispatch_outbox(self, *, ctx: PipelineContext) -> None:
        """
        Step 17 — Post-commit outbox dispatch (Section 13.6.17).

        Outbox events were queued to ctx during steps 5-15 and persisted
        atomically in Tx B. This step triggers async dispatch (fire-and-forget).
        Dispatch failure is non-blocking.
        """
        if not ctx.outbox_events:
            logger.debug(
                "[pipeline:step] outbox_dispatch no_events entry=%s run=%s",
                ctx.entry_id,
                ctx.processing_run_id,
            )
            return

        logger.info(
            "[pipeline:step] outbox_dispatch events=%d entry=%s run=%s",
            len(ctx.outbox_events),
            ctx.entry_id,
            ctx.processing_run_id,
        )
        # Actual async dispatch is handled by a background worker that polls
        # the outbox_events table. We just log here.
        for evt in ctx.outbox_events:
            logger.debug(
                "[pipeline:step] outbox_event type=%s entry=%s run=%s",
                evt.get("event_type"),
                ctx.entry_id,
                ctx.processing_run_id,
            )

    # ------------------------------------------------------------------
    # Failure recording helpers
    # ------------------------------------------------------------------

    def _try_mark_failed(
        self,
        *,
        orchestrator: TransactionOrchestrator,
        job_id: str,
        entry_id: str,
        error_code: str,
        error_message: str,
        processing_run_id: str,
    ) -> None:
        """Best-effort: mark job+entry as failed without raising."""
        try:
            orchestrator.mark_job_failed(
                job_id=job_id,
                error_code=error_code,
                error_message=error_message,
                entry_id=entry_id,
                processing_run_id=processing_run_id,
            )
        except Exception as exc:
            logger.exception(
                "[pipeline:fatal] mark_failed_failed job=%s entry=%s: %s",
                job_id,
                entry_id,
                exc,
            )

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    def _assemble_success_result(
        self,
        *,
        ctx: PipelineContext,
        entry_id: str,
        job_id: str,
        records: List[_StepRecord],
        processing_duration_ms: int,
        now_utc_iso: str,
    ) -> Dict[str, Any]:
        fallbacks = [r for r in records if r.status == "fallback"]
        succeeded = [r for r in records if r.status == "succeeded"]

        personality_result = ctx.personality_result or {}
        xp_result = ctx.xp_result or {}
        quest_result = dict(ctx.quest_result or {})
        insight_result = ctx.insight_result or {}
        harmony_result = ctx.harmony_result or {}
        anomaly_result = ctx.anomaly_result or {}
        arc_result = ctx.arc_result or {}
        strategy_result = ctx.strategy_result or {}
        structured_data = ctx.structured_data or {}
        variety_result = ctx.variety_result or {}

        quest_result.setdefault(
            "xp_lineage",
            _build_xp_lineage(structured_data=structured_data, xp_result=xp_result),
        )

        quality = _build_quality_payload(records)
        step_trace = _build_step_trace(records)
        summary = _build_summary_payload(
            structured_data=structured_data,
            strategy_result=strategy_result,
            variety_result=variety_result,
            quest_result=quest_result,
            anomaly_result=anomaly_result,
            insight_result=insight_result,
            xp_result=xp_result,
        )
        provenance = _build_provenance_payload(
            ctx=ctx,
            quality=quality,
            insight_result=insight_result,
            personality_result=personality_result,
        )

        return asdict(
            PipelineSuccessResult(
                entry_id=entry_id,
                user_id=ctx.user_id,
                created_at_utc=_iso_z(ctx.time.created_at_utc),
                processing_started_at_utc=_iso_z(ctx.time.processing_started_at_utc),
                processing_completed_at_utc=now_utc_iso,
                local_event_date=ctx.time.local_event_date,
                structured_data=structured_data,
                safety_result=ctx.safety_result or {},
                forgiveness_result=ctx.forgiveness_result or {},
                strategy_result=strategy_result,
                variety_result=variety_result,
                quest_result=quest_result,
                anomaly_result=anomaly_result,
                harmony_result=harmony_result,
                insight_result=insight_result,
                arc_result=arc_result,
                xp_result=xp_result,
                personality_result=personality_result,
                report_result=ctx.report_result or {},
                personality_messages=[],  # loaded from DB in Tx B
                active_personality=personality_result.get("personality"),
                message=personality_result.get("message", ""),
                message_id=personality_result.get("message_id"),
                personality=personality_result.get("personality"),
                processing_duration_ms=processing_duration_ms,
                steps_attempted=len(records),
                steps_succeeded=len(succeeded),
                steps_fallbacked=len(fallbacks),
                noncritical_errors=ctx.errors,
                pipeline_version=PIPELINE_VERSION,
                ruleset_version=RULESET_VERSION,
                processing_run_id=ctx.processing_run_id,
                job_id=job_id,
                degraded=bool(quality.get("degraded")),
                degraded_codes=list(quality.get("degraded_codes", [])),
                summary=summary,
                meta=quality,
                step_trace=step_trace,
                quality=quality,
                provenance=provenance,
            )
        )

    def _build_already_finalised_result(
        self,
        *,
        ctx: PipelineContext,
        entry_id: str,
        job_id: str,
    ) -> Dict[str, Any]:
        return {
            "result_type": "already_finalised",
            "entry_id": entry_id,
            "user_id": ctx.user_id,
            "job_id": job_id,
            "processing_run_id": ctx.processing_run_id,
            "status": "completed",
            "pipeline_version": PIPELINE_VERSION,
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _iso_z(ts: Any) -> str:
    """Convert a datetime or ISO string to Z-suffixed UTC string."""
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return str(ts).replace("+00:00", "Z")


def _serialize_quest(quest: Any) -> Dict[str, Any]:
    return {
        "quest_id": quest.id,
        "quest_type": getattr(quest, "quest_type", None),
        "completion_type": getattr(quest, "completion_type", None),
        "status": getattr(quest, "status", None),
    }


def _serialize_xp_award(award: Any) -> Dict[str, Any]:
    return {
        "id": getattr(award, "id", None),
        "quest_id": getattr(award, "quest_id", None),
        "skill_id": getattr(award, "skill_id", None),
        "theme_id": getattr(award, "theme_id", None),
        "distribution_type": getattr(award, "distribution_type", None),
        "amount": getattr(award, "amount", 0),
        "xp_reason": getattr(award, "xp_reason", None),
    }
