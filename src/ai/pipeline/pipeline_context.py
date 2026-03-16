"""
Pipeline context for deterministic, reproducible processing.

Implements Section 13.3 (Pipeline Context) and Section 13.4 (Time Semantics
and Version Snapshots) from COMPLETE_ARCHITECTURE.md.

Design invariants
-----------------
* TimeContext is frozen at ``create_pipeline_context`` call time.
  No subsystem may call ``datetime.utcnow()`` / ``datetime.now()`` after that.
* VersionSnapshot captures AI model IDs, prompt template versions, and
  config thresholds once at Step 2. Values are never re-read from config
  or the database during a pipeline run.
* Step outputs are accumulated on ``PipelineContext`` by the orchestrator
  and flushed in a single atomic Tx B.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytz

from src.ai.runtime_config import get_ollama_defaults

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt version registry
# ---------------------------------------------------------------------------
# In a future iteration these will be read from a DB table or a versioned
# file. For now they are env-overridable constants so that the pipeline
# context is still reproducible when the env is pinned.

_PROMPT_VERSIONS: Dict[str, str] = {
    "categorization": os.getenv("PROMPT_VERSION_CATEGORIZATION", "v1"),
    "quest_generation": os.getenv("PROMPT_VERSION_QUEST_GENERATION", "v3"),
    "insight_extraction": os.getenv("PROMPT_VERSION_INSIGHT_EXTRACTION", "v1"),
    "personality_message": os.getenv("PROMPT_VERSION_PERSONALITY_MESSAGE", "v2"),
}

# ---------------------------------------------------------------------------
# Config defaults (override via env for testing / deployment)
# ---------------------------------------------------------------------------

_FAILURE_PENALTY_THRESHOLD = float(
    os.getenv("CONFIG_FAILURE_PENALTY_THRESHOLD", "0.5")
)


def _load_variety_bonus_config() -> Dict[str, Any]:
    """Return frozen variety-bonus config from env / defaults."""
    return {
        "min_distinct_categories": int(
            os.getenv("VARIETY_BONUS_MIN_DISTINCT_CATEGORIES", "3")
        ),
        "bonus_xp": int(os.getenv("VARIETY_BONUS_XP", "25")),
        "lookback_days": int(os.getenv("VARIETY_BONUS_LOOKBACK_DAYS", "7")),
    }


def _load_arc_multiplier_config() -> Dict[str, Any]:
    """Return frozen arc-multiplier config from env / defaults."""
    return {
        "base_multiplier": float(os.getenv("ARC_MULTIPLIER_BASE", "1.0")),
        "max_multiplier": float(os.getenv("ARC_MULTIPLIER_MAX", "2.0")),
        "decay_per_day": float(os.getenv("ARC_MULTIPLIER_DECAY_PER_DAY", "0.05")),
    }


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeContext:
    """
    Frozen time semantics (Section 13.4.2).

    All fields are set once at context creation and never mutated.
    Subsystems receive this object and must not perform wall-clock reads.
    """

    created_at_utc: datetime
    """Original entry creation timestamp (UTC, timezone-aware)."""

    processing_started_at_utc: datetime
    """Pipeline start timestamp captured at context creation (UTC, tz-aware)."""

    local_event_date: str
    """YYYY-MM-DD date in the user's local timezone, derived from created_at_utc."""

    user_timezone_at_ingest: str
    """IANA timezone string recorded at entry ingestion time."""


@dataclass(frozen=True)
class VersionSnapshot:
    """
    Immutable version snapshot (Section 13.4.3).

    Captured once at Step 2 and stored on the processing job row so that
    any future replay can reconstruct the exact configuration used.
    """

    # AI model
    ai_model_id: str
    ai_model_version: str

    # Prompt template versions
    categorization_prompt_version: str
    quest_generation_prompt_version: str
    insight_extraction_prompt_version: str
    personality_message_prompt_version: str

    # Config thresholds (frozen)
    failure_penalty_threshold: float
    variety_bonus_config: Dict[str, Any]
    arc_multiplier_config: Dict[str, Any]

    def as_json_dict(self) -> Dict[str, Any]:
        """Serialise for storage in processing_jobs.ai_version_snapshot."""
        return {
            "ai_model_id": self.ai_model_id,
            "ai_model_version": self.ai_model_version,
            "categorization_prompt_version": self.categorization_prompt_version,
            "quest_generation_prompt_version": self.quest_generation_prompt_version,
            "insight_extraction_prompt_version": self.insight_extraction_prompt_version,
            "personality_message_prompt_version": self.personality_message_prompt_version,
            "failure_penalty_threshold": self.failure_penalty_threshold,
            "variety_bonus_config": self.variety_bonus_config,
            "arc_multiplier_config": self.arc_multiplier_config,
        }


@dataclass
class PipelineContext:
    """
    Complete pipeline execution context (Section 13.3).

    Maintains frozen timestamps and version snapshots alongside mutable
    step outputs that accumulate during processing.  The orchestrator writes
    all outputs atomically in Tx B once all steps complete.

    Step output fields
    ------------------
    Each field is ``None`` until the corresponding step populates it.
    A ``None`` value means the step was skipped or produced no output.
    A dict value is the raw step result; the orchestrator decides how
    to persist it in Tx B.
    """

    # Identity
    user_id: str
    entry_id: str
    processing_run_id: str
    idempotency_key: str

    # Time (frozen at creation — must NOT be mutated)
    time: TimeContext

    # Versions (frozen at Step 2 — must NOT be mutated)
    versions: VersionSnapshot

    # ------------------------------------------------------------------ #
    # Step outputs (populated during processing, outside any transaction)  #
    # ------------------------------------------------------------------ #

    # Step 3 — Structured extraction
    structured_data: Optional[Dict[str, Any]] = None

    # Step 4 — Safety / crisis detection
    safety_result: Optional[Dict[str, Any]] = None

    # Step 5 — Forgiveness / self-compassion analysis
    forgiveness_result: Optional[Dict[str, Any]] = None

    # Step 6 — Strategy tracking
    strategy_result: Optional[Dict[str, Any]] = None

    # Step 7 — Variety bonus evaluation
    variety_result: Optional[Dict[str, Any]] = None

    # Step 8 — Quest matching + generation
    quest_result: Optional[Dict[str, Any]] = None

    # Step 9 — Anomaly scoring
    anomaly_result: Optional[Dict[str, Any]] = None

    # Step 10 — Harmony dimension scoring
    harmony_result: Optional[Dict[str, Any]] = None

    # Step 11 — Insight extraction (LLM + RAG)
    insight_result: Optional[Dict[str, Any]] = None

    # Step 12 — Story arc evaluation
    arc_result: Optional[Dict[str, Any]] = None

    # Step 13 — XP calculation + award
    xp_result: Optional[Dict[str, Any]] = None

    # Step 14 — Personality message generation (LLM + RAG)
    personality_result: Optional[Dict[str, Any]] = None

    # Step 15b — System report (deterministic, no LLM)
    report_result: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ #
    # Cross-cutting accumulators                                           #
    # ------------------------------------------------------------------ #

    errors: List[Dict[str, Any]] = field(default_factory=list)
    """Per-step error records.  Non-fatal errors are accumulated here
    rather than raising, allowing the pipeline to continue in degraded mode."""

    outbox_events: List[Dict[str, Any]] = field(default_factory=list)
    """Outbox events queued during processing. Persisted atomically in Tx B."""

    def add_error(
        self,
        step: str,
        error_code: str,
        message: str,
        *,
        fatal: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a step error and emit a structured log entry."""
        record = {
            "step": step,
            "error_code": error_code,
            "message": message,
            "fatal": fatal,
            **(extra or {}),
        }
        self.errors.append(record)
        log_ctx = {
            "pipeline_ctx": {
                "user_id": self.user_id,
                "entry_id": self.entry_id,
                "processing_run_id": self.processing_run_id,
                "step": step,
                "error_code": error_code,
                "fatal": fatal,
            }
        }
        if fatal:
            logger.error(
                "[pipeline:error] step=%s error_code=%s fatal=True msg=%s",
                step,
                error_code,
                message,
                extra=log_ctx,
            )
        else:
            logger.warning(
                "[pipeline:error] step=%s error_code=%s fatal=False msg=%s",
                step,
                error_code,
                message,
                extra=log_ctx,
            )

    def queue_outbox_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Enqueue an outbox event for atomic persistence in Tx B."""
        self.outbox_events.append({"event_type": event_type, "payload": payload})
        logger.debug(
            "[pipeline:outbox] Queued event type=%s entry=%s run=%s",
            event_type,
            self.entry_id,
            self.processing_run_id,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_pipeline_context(
    user_id: str,
    entry_id: str,
    processing_run_id: str,
    idempotency_key: str,
    user_timezone: str,
    created_at_utc: datetime,
) -> PipelineContext:
    """
    Create a fully-initialised ``PipelineContext`` with frozen time and
    version snapshots.

    This is the ONLY place where ``datetime.now()`` may be called during
    pipeline setup.  All subsystems receive a ``PipelineContext`` and must
    use ``ctx.time.*`` fields rather than reading the wall clock.

    Args:
        user_id:            Owner of the entry.
        entry_id:           Journal entry being processed.
        processing_run_id:  Unique run identifier (UUID string).
        idempotency_key:    Caller-supplied replay key.
        user_timezone:      IANA timezone string (e.g. ``"America/New_York"``).
        created_at_utc:     Entry creation timestamp (must be UTC).

    Returns:
        Initialised :class:`PipelineContext`.

    Raises:
        pytz.exceptions.UnknownTimeZoneError: If ``user_timezone`` is invalid.
    """
    # --- Frozen timestamps -----------------------------------------------
    processing_started_at = datetime.now(timezone.utc)

    # Normalise created_at_utc to be timezone-aware (defensive).
    if created_at_utc.tzinfo is None:
        created_at_utc = created_at_utc.replace(tzinfo=timezone.utc)

    tz = pytz.timezone(user_timezone)
    local_dt = created_at_utc.astimezone(tz)
    local_event_date = local_dt.strftime("%Y-%m-%d")

    time_ctx = TimeContext(
        created_at_utc=created_at_utc,
        processing_started_at_utc=processing_started_at,
        local_event_date=local_event_date,
        user_timezone_at_ingest=user_timezone,
    )

    # --- Version snapshot (Step 2) ----------------------------------------
    # AI model from runtime config (env / YAML — same source as ollama client).
    _base_url, ai_model_id, _timeout = get_ollama_defaults()
    # Model tag normalisation: strip ":latest" for the version field.
    if ":" in ai_model_id:
        model_name, model_tag = ai_model_id.rsplit(":", 1)
    else:
        model_name, model_tag = ai_model_id, "latest"

    versions = VersionSnapshot(
        ai_model_id=model_name,
        ai_model_version=model_tag,
        categorization_prompt_version=_PROMPT_VERSIONS["categorization"],
        quest_generation_prompt_version=_PROMPT_VERSIONS["quest_generation"],
        insight_extraction_prompt_version=_PROMPT_VERSIONS["insight_extraction"],
        personality_message_prompt_version=_PROMPT_VERSIONS["personality_message"],
        failure_penalty_threshold=_FAILURE_PENALTY_THRESHOLD,
        variety_bonus_config=_load_variety_bonus_config(),
        arc_multiplier_config=_load_arc_multiplier_config(),
    )

    log_ctx = {
        "pipeline_ctx": {
            "user_id": user_id,
            "entry_id": entry_id,
            "processing_run_id": processing_run_id,
            "local_event_date": local_event_date,
            "user_timezone": user_timezone,
            "ai_model_id": model_name,
            "ai_model_version": model_tag,
        }
    }
    logger.info(
        "[pipeline:context] Created pipeline context entry=%s run=%s "
        "local_date=%s model=%s:%s",
        entry_id,
        processing_run_id,
        local_event_date,
        model_name,
        model_tag,
        extra=log_ctx,
    )
    logger.debug(
        "[pipeline:llm] LLM version snapshot captured model=%s version=%s "
        "cat_prompt=%s quest_prompt=%s insight_prompt=%s personality_prompt=%s",
        model_name,
        model_tag,
        versions.categorization_prompt_version,
        versions.quest_generation_prompt_version,
        versions.insight_extraction_prompt_version,
        versions.personality_message_prompt_version,
        extra=log_ctx,
    )

    return PipelineContext(
        user_id=user_id,
        entry_id=entry_id,
        processing_run_id=processing_run_id,
        idempotency_key=idempotency_key,
        time=time_ctx,
        versions=versions,
    )
