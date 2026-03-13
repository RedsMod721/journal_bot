"""MB82 — Align Section 13 control-plane tables and personality message schema.

Revision ID: b10000000019
Revises: b10000000018
Create Date: 2026-03-13 23:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b10000000019"
down_revision = "b10000000018"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    op.execute("PRAGMA foreign_keys=OFF")

    for table_name in (
        "outbox_events",
        "processing_job_claims",
        "processing_job_attempts",
        "entry_idempotency_claims",
        "processing_jobs",
    ):
        if _table_exists(bind, table_name):
            op.drop_table(table_name)

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("entry_id", sa.String(36), nullable=False),
        sa.Column("step_name", sa.String(64), nullable=False),
        sa.Column("processing_run_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_payload_hash", sa.String(64), nullable=True),
        sa.Column("final_error_code", sa.String(100), nullable=True),
        sa.Column("final_error_message", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("request_payload_hash", sa.String(64), nullable=True),
        sa.Column("pipeline_version", sa.String(50), nullable=True),
        sa.Column("ruleset_version", sa.String(50), nullable=True),
        sa.Column("config_version", sa.String(50), nullable=True),
        sa.Column("ai_version_snapshot", sa.Text(), nullable=True),
        sa.Column("prompt_version_snapshot", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_processing_jobs_user_entry",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_processing_jobs"),
        sa.UniqueConstraint(
            "user_id",
            "entry_id",
            "step_name",
            "processing_run_id",
            name="uq_processing_jobs_logical",
        ),
        sa.CheckConstraint(
            "status IN ('in_progress','succeeded','failed')",
            name="ck_processing_jobs_status",
        ),
        sa.CheckConstraint(
            "step_name IN ("
            "'categorization',"
            "'quest_generation',"
            "'insight_extraction',"
            "'voice_transcription',"
            "'report_generation',"
            "'personality_message_generation',"
            "'entry_pipeline'"
            ")",
            name="ck_processing_jobs_step_name",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_processing_jobs_attempt_count",
        ),
    )
    op.create_index(
        "idx_processing_jobs_job",
        "processing_jobs",
        ["user_id", "entry_id", "step_name"],
    )
    op.create_index(
        "idx_processing_jobs_run",
        "processing_jobs",
        ["user_id", "processing_run_id"],
    )
    op.create_index(
        "idx_processing_jobs_status_updated",
        "processing_jobs",
        ["status", "updated_at"],
    )
    op.execute(
        "CREATE INDEX idx_processing_jobs_entry_pipeline "
        "ON processing_jobs(user_id, entry_id, step_name, status) "
        "WHERE step_name = 'entry_pipeline'"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_processing_jobs_one_success "
        "ON processing_jobs(user_id, entry_id, step_name) "
        "WHERE status = 'succeeded'"
    )
    op.execute(
        """
        CREATE TRIGGER trg_processing_jobs_updated_at
        AFTER UPDATE ON processing_jobs
        FOR EACH ROW
        BEGIN
          UPDATE processing_jobs
          SET updated_at = (datetime('now'))
          WHERE id = NEW.id;
        END;
        """
    )

    op.create_table(
        "processing_job_attempts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("processing_job_id", sa.String(36), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column("executor_type", sa.String(20), nullable=False),
        sa.Column("node_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["processing_job_id"],
            ["processing_jobs.id"],
            ondelete="CASCADE",
            name="fk_processing_job_attempts_job",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_processing_job_attempts"),
        sa.UniqueConstraint(
            "processing_job_id",
            "attempt_id",
            name="uq_processing_job_attempts_job_attempt",
        ),
        sa.CheckConstraint("attempt_id >= 1", name="ck_processing_job_attempts_attempt_id"),
        sa.CheckConstraint(
            "executor_type IN ('server_local','trusted_node')",
            name="ck_processing_job_attempts_executor_type",
        ),
        sa.CheckConstraint(
            "status IN ('succeeded','failed','rejected','timeout')",
            name="ck_processing_job_attempts_status",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_processing_job_attempts_duration_ms",
        ),
    )
    op.create_index(
        "idx_processing_job_attempts_job",
        "processing_job_attempts",
        ["processing_job_id"],
    )
    op.create_index(
        "idx_processing_job_attempts_time",
        "processing_job_attempts",
        ["attempted_at"],
    )

    op.create_table(
        "entry_idempotency_claims",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_payload_hash", sa.String(64), nullable=True),
        sa.Column("entry_id", sa.String(36), nullable=True),
        sa.Column("processing_job_id", sa.String(36), nullable=True),
        sa.Column("processing_run_id", sa.String(36), nullable=True),
        sa.Column("result_pointer_json", sa.Text(), nullable=True),
        sa.Column("final_error_code", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="reserved"),
        sa.Column(
            "claimed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="SET NULL",
            name="fk_entry_claims_user_entry",
        ),
        sa.ForeignKeyConstraint(
            ["processing_job_id"],
            ["processing_jobs.id"],
            ondelete="SET NULL",
            name="fk_entry_claims_processing_job",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_entry_idempotency_claims"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_entry_claims_user_key"),
        sa.CheckConstraint(
            "status IN ('reserved','in_progress','completed','failed_retryable','failed_terminal')",
            name="ck_entry_claims_status",
        ),
    )
    op.create_index("idx_entry_claims_user", "entry_idempotency_claims", ["user_id"])
    op.create_index(
        "idx_entry_claims_status",
        "entry_idempotency_claims",
        ["status", "updated_at"],
    )
    op.create_index(
        "idx_entry_claims_job",
        "entry_idempotency_claims",
        ["processing_job_id"],
    )
    op.create_index(
        "idx_entry_claims_entry",
        "entry_idempotency_claims",
        ["user_id", "entry_id"],
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("entry_id", sa.String(36), nullable=True),
        sa.Column("processing_job_id", sa.String(36), nullable=True),
        sa.Column("processing_run_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_dedupe_key", sa.String(255), nullable=False),
        sa.Column("destination", sa.String(100), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("lease_owner_token", sa.String(100), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_outbox_events_user_entry",
        ),
        sa.ForeignKeyConstraint(
            ["processing_job_id"],
            ["processing_jobs.id"],
            ondelete="SET NULL",
            name="fk_outbox_events_processing_job",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
        sa.UniqueConstraint("event_dedupe_key", name="uq_outbox_events_dedupe"),
        sa.CheckConstraint(
            "status IN ('pending','dispatching','succeeded','failed_retryable','failed_terminal')",
            name="ck_outbox_events_status",
        ),
        sa.CheckConstraint("retry_count >= 0", name="ck_outbox_events_retry_count"),
    )
    op.create_index(
        "idx_outbox_events_status_next_attempt",
        "outbox_events",
        ["status", "next_attempt_at", "created_at"],
    )
    op.create_index(
        "idx_outbox_events_lease",
        "outbox_events",
        ["status", "lease_expires_at"],
    )
    op.create_index(
        "idx_outbox_events_source_run",
        "outbox_events",
        ["processing_run_id"],
    )
    op.create_index(
        "idx_outbox_events_user_entry",
        "outbox_events",
        ["user_id", "entry_id"],
    )

    op.create_table(
        "processing_job_claims",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("entry_id", sa.String(36), nullable=False),
        sa.Column("step_name", sa.String(64), nullable=False),
        sa.Column("owner_kind", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.String(100), nullable=False),
        sa.Column("lease_token", sa.String(64), nullable=False),
        sa.Column(
            "claimed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "heartbeat_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id", "entry_id"],
            ["journal_entries.user_id", "journal_entries.id"],
            ondelete="CASCADE",
            name="fk_processing_job_claims_user_entry",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_processing_job_claims"),
        sa.UniqueConstraint(
            "user_id",
            "entry_id",
            "step_name",
            name="uq_processing_job_claims_logical",
        ),
        sa.UniqueConstraint("lease_token", name="uq_processing_job_claims_lease_token"),
        sa.CheckConstraint(
            "owner_kind IN ('server_worker','scheduler','admin_recovery')",
            name="ck_processing_job_claims_owner_kind",
        ),
    )
    op.create_index(
        "idx_processing_job_claims_lease_expiry",
        "processing_job_claims",
        ["lease_expires_at"],
    )
    op.create_index(
        "idx_processing_job_claims_owner",
        "processing_job_claims",
        ["owner_kind", "owner_id"],
    )

    personality_old = False
    if _table_exists(bind, "personality_messages"):
        personality_old = True
        for index_name in (
            "idx_personality_messages_user",
            "idx_personality_messages_entry",
            "idx_personality_messages_user_entry",
            "idx_personality_messages_user_entry_type",
            "idx_personality_messages_selector_seed",
            "uq_personality_messages_selector_slot",
            "uq_personality_messages_exactly_once",
        ):
            op.execute(f"DROP INDEX IF EXISTS {index_name}")
        op.rename_table("personality_messages", "personality_messages__mb82_old")

    op.create_table(
        "personality_messages",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("entry_id", sa.String(36), nullable=False),
        sa.Column("personality", sa.String(50), nullable=False),
        sa.Column("message_type", sa.String(50), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("selector_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("selector_seed_hash", sa.String(64), nullable=True),
        sa.Column("logical_slot_key", sa.String(100), nullable=False, server_default="default"),
        sa.Column("context_data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("quest_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entry_id"], ["journal_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quest_id"], ["quests.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_personality_messages"),
        sa.UniqueConstraint(
            "user_id",
            "entry_id",
            "message_type",
            "logical_slot_key",
            "selector_version",
            name="uq_personality_messages_selector_slot",
        ),
        sa.CheckConstraint(
            "personality IN ('observer','therapist','coach','sassy','wargod','raphael')",
            name="ck_personality_messages_personality",
        ),
        sa.CheckConstraint(
            "message_type IN ("
            "'entry_feedback','quest_complete','level_up','arc_trigger',"
            "'safety_intervention','entry_ack','quest_nudge','report_summary'"
            ")",
            name="ck_personality_messages_message_type",
        ),
    )
    op.create_index("idx_personality_messages_user", "personality_messages", ["user_id"])
    op.create_index("idx_personality_messages_entry", "personality_messages", ["entry_id"])
    op.create_index(
        "idx_personality_messages_user_entry",
        "personality_messages",
        ["user_id", "entry_id"],
    )
    op.create_index(
        "idx_personality_messages_user_entry_type",
        "personality_messages",
        ["user_id", "entry_id", "message_type"],
    )
    op.create_index(
        "idx_personality_messages_selector_seed",
        "personality_messages",
        ["user_id", "selector_seed_hash"],
    )

    if personality_old:
        op.execute(
            """
            INSERT INTO personality_messages (
                id, user_id, entry_id, personality, message_type, message_text,
                selector_version, selector_seed_hash, logical_slot_key,
                context_data, quest_id, created_at
            )
            SELECT
                id,
                user_id,
                entry_id,
                personality,
                message_type,
                message_text,
                COALESCE(selector_version, 1),
                selector_seed_hash,
                COALESCE(logical_slot_key, 'default'),
                COALESCE(context_data, '{}'),
                quest_id,
                created_at
            FROM personality_messages__mb82_old
            """
        )
        op.drop_table("personality_messages__mb82_old")

    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    raise RuntimeError("MB82 downgrade is not supported")
