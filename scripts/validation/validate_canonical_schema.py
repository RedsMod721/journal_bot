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
}


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

    print(f"Found tables: {len(tables)}")
    if extra_tables:
        print(f"Additional non-canonical tables: {', '.join(extra_tables)}")

    if ok:
        print("Canonical schema validation passed.")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
