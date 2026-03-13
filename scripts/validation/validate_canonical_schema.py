"""Validate canonical schema inventory and core trigger/index invariants."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect, text

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.db.session import engine

CANONICAL_TABLES = {
    "users",
    "journal_entries",
    "journal_entries_structured",
    "entry_attachments",
    "skills",
    "themes",
    "skill_theme_mappings",
    "quests",
    "quest_failure_tracker",
    "xp_awards",
    "user_quest_preferences",
    "user_quest_biases",
    "leisure_budget",
    "substance_limits",
    "substance_usage_log",
    "quest_templates",
    "quest_progress",
    "story_arcs",
    "arc_triggers",
    "personality_states",
    "personality_messages",
    "personality_memory",
    "rag_documents",
    "forgiveness_configs",
    "decay_snapshots",
    "harmony_dimensions",
    "harmony_snapshots",
    "patterns",
    "insights",
    "insight_evidence",
    "strategy_tracking",
    "anomaly_scores",
    "global_skills",
    "global_quests",
    "global_insights",
    "kb_contributions",
    "level_ups",
    "user_analytics",
    "roles",
    "user_roles",
    "refresh_tokens",
    "server_config",
    "entry_idempotency_claims",
    "outbox_events",
    "processing_jobs",
    "processing_job_attempts",
    "processing_job_claims",
    "trusted_nodes",
    "node_tokens",
    "node_task_assignments",
    "node_task_results",
    "node_audit_log",
}

REQUIRED_TRIGGERS = {
    "trg_personality_messages_quest_user",
    "trg_personality_messages_quest_user_upd",
    "trg_personality_messages_entry_user",
    "trg_personality_messages_entry_user_upd",
    "trg_quests_entry_user",
    "trg_quests_entry_user_upd",
}

REQUIRED_COLUMNS = {
    "entry_idempotency_claims": {
        "processing_job_id",
        "request_payload_hash",
        "result_pointer_json",
        "final_error_code",
    },
    "outbox_events": {
        "entry_id",
        "processing_job_id",
        "processing_run_id",
        "destination",
        "payload_hash",
        "next_attempt_at",
        "lease_owner_token",
        "lease_expires_at",
        "last_error_message",
        "dispatched_at",
    },
    "processing_jobs": {
        "attempt_count",
        "finalized_at",
        "final_payload_hash",
        "final_error_code",
        "final_error_message",
        "request_payload_hash",
        "pipeline_version",
        "ruleset_version",
        "config_version",
        "ai_version_snapshot",
        "prompt_version_snapshot",
    },
    "personality_messages": {
        "selector_version",
        "selector_seed_hash",
        "logical_slot_key",
        "context_data",
    },
}

REQUIRED_INDEX_COLUMNS = {
    "entry_idempotency_claims": {
        "idx_entry_claims_job": ("processing_job_id",),
        "idx_entry_claims_entry": ("user_id", "entry_id"),
    },
    "outbox_events": {
        "uq_outbox_events_dedupe": ("event_dedupe_key",),
        "idx_outbox_events_status_next_attempt": ("status", "next_attempt_at", "created_at"),
        "idx_outbox_events_lease": ("status", "lease_expires_at"),
        "idx_outbox_events_source_run": ("processing_run_id",),
        "idx_outbox_events_user_entry": ("user_id", "entry_id"),
    },
    "processing_jobs": {
        "idx_processing_jobs_job": ("user_id", "entry_id", "step_name"),
        "idx_processing_jobs_run": ("user_id", "processing_run_id"),
        "idx_processing_jobs_status_updated": ("status", "updated_at"),
        "idx_processing_jobs_entry_pipeline": ("user_id", "entry_id", "step_name", "status"),
        "uq_processing_jobs_one_success": ("user_id", "entry_id", "step_name"),
    },
    "processing_job_attempts": {
        "idx_processing_job_attempts_job": ("processing_job_id",),
        "idx_processing_job_attempts_time": ("attempted_at",),
    },
    "personality_messages": {
        "uq_personality_messages_selector_slot": (
            "user_id",
            "entry_id",
            "message_type",
            "logical_slot_key",
            "selector_version",
        ),
        "idx_personality_messages_selector_seed": ("user_id", "selector_seed_hash"),
    },
}

REQUIRED_SQL_SNIPPETS = {
    "processing_jobs": (
        "step_name in ('categorization','quest_generation','insight_extraction','voice_transcription','report_generation','personality_message_generation','entry_pipeline')",
    ),
    "processing_job_attempts": (
        "attempt_id",
        "attempted_at",
        "executor_type",
        "payload_hash",
        "error_message",
        "duration_ms",
        "status in ('succeeded','failed','rejected','timeout')",
        "executor_type in ('server_local','trusted_node')",
    ),
    "personality_messages": (
        "message_type in ('entry_feedback','quest_complete','level_up','arc_trigger','safety_intervention','entry_ack','quest_nudge','report_summary')",
    ),
}

REQUIRED_FK_TABLES = {
    "entry_idempotency_claims": {
        ("user_id",): "users",
        ("processing_job_id",): "processing_jobs",
    },
    "outbox_events": {
        ("user_id",): "users",
        ("processing_job_id",): "processing_jobs",
    },
    "processing_jobs": {
        ("user_id",): "users",
    },
    "processing_job_claims": {
        ("user_id",): "users",
    },
}


def _normalize_sql(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def main() -> int:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    missing_tables = sorted(CANONICAL_TABLES - tables)
    extra_tables = sorted(tables - CANONICAL_TABLES - {"alembic_version"})

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='trigger'")
        ).fetchall()
    triggers = {row[0] for row in rows}
    missing_triggers = sorted(REQUIRED_TRIGGERS - triggers)
    missing_columns: list[str] = []
    missing_indexes: list[str] = []
    missing_sql_invariants: list[str] = []
    missing_fks: list[str] = []
    for table_name, required_columns in REQUIRED_COLUMNS.items():
        present_columns = {
            col["name"] for col in inspector.get_columns(table_name)
        }
        missing = sorted(required_columns - present_columns)
        if missing:
            missing_columns.append(f"{table_name}: {', '.join(missing)}")

    for table_name, required_indexes in REQUIRED_INDEX_COLUMNS.items():
        indexes = {
            index["name"]: tuple(index.get("column_names") or [])
            for index in inspector.get_indexes(table_name)
        }
        uniques = {
            index["name"]: tuple(index.get("column_names") or [])
            for index in inspector.get_unique_constraints(table_name)
        }
        available = {**indexes, **uniques}
        for index_name, expected_columns in required_indexes.items():
            if available.get(index_name) != expected_columns:
                missing_indexes.append(
                    f"{table_name}.{index_name} -> expected {expected_columns}, found {available.get(index_name)}"
                )

    with engine.connect() as conn:
        table_sql_rows = conn.execute(
            text(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type IN ('table','index') AND sql IS NOT NULL"
            )
        ).fetchall()
    object_sql = {row[0]: _normalize_sql(row[1]) for row in table_sql_rows}

    for object_name, snippets in REQUIRED_SQL_SNIPPETS.items():
        normalized = object_sql.get(object_name, "")
        for snippet in snippets:
            if _normalize_sql(snippet) not in normalized:
                missing_sql_invariants.append(f"{object_name}: missing `{snippet}`")

    for table_name, required_fks in REQUIRED_FK_TABLES.items():
        fk_rows = inspector.get_foreign_keys(table_name)
        available = {
            tuple(fk.get("constrained_columns") or []): fk.get("referred_table")
            for fk in fk_rows
        }
        for columns, referred_table in required_fks.items():
            if available.get(columns) != referred_table:
                missing_fks.append(
                    f"{table_name}: FK {columns} -> {referred_table} missing (found {available.get(columns)})"
                )

    ok = True
    if missing_tables:
        ok = False
        print(f"Missing tables ({len(missing_tables)}): {', '.join(missing_tables)}")
    if missing_triggers:
        ok = False
        print(
            f"Missing required triggers ({len(missing_triggers)}): "
            f"{', '.join(missing_triggers)}"
        )
    if missing_columns:
        ok = False
        print(
            f"Missing required columns ({len(missing_columns)}): "
            + "; ".join(missing_columns)
        )
    if missing_indexes:
        ok = False
        print(
            f"Missing required indexes ({len(missing_indexes)}): "
            + "; ".join(missing_indexes)
        )
    if missing_sql_invariants:
        ok = False
        print(
            f"Missing required SQL invariants ({len(missing_sql_invariants)}): "
            + "; ".join(missing_sql_invariants)
        )
    if missing_fks:
        ok = False
        print(
            f"Missing required foreign keys ({len(missing_fks)}): "
            + "; ".join(missing_fks)
        )

    print(f"Found tables: {len(tables)}")
    if extra_tables:
        print(f"Additional non-canonical tables: {', '.join(extra_tables)}")

    if ok:
        print("Canonical schema validation passed.")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
