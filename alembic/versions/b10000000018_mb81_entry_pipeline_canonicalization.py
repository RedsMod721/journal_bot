"""MB81 — Canonicalize entry pipeline control-plane tables and personality guards.

Revision ID: b10000000018
Revises: b10000000017
Create Date: 2026-03-13 18:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b10000000018"
down_revision = "b10000000017"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    # Rebuild the operational control-plane tables to align statuses/columns.
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
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.ForeignKeyConstraint(
            ["processing_job_id"],
            ["processing_jobs.id"],
            ondelete="CASCADE",
            name="fk_processing_job_attempts_job",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_processing_job_attempts"),
        sa.UniqueConstraint(
            "processing_job_id",
            "attempt_number",
            name="uq_processing_job_attempts_job_attempt",
        ),
        sa.CheckConstraint(
            "attempt_number > 0",
            name="ck_processing_job_attempts_attempt_number",
        ),
        sa.CheckConstraint(
            "status IN ('started','completed','failed')",
            name="ck_processing_job_attempts_status",
        ),
    )
    op.create_index(
        "idx_processing_job_attempts_job",
        "processing_job_attempts",
        ["processing_job_id"],
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
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_entry_claims_user_key",
        ),
        sa.CheckConstraint(
            "status IN ('reserved','in_progress','completed','failed_retryable','failed_terminal')",
            name="ck_entry_claims_status",
        ),
    )
    op.create_index(
        "idx_entry_claims_user",
        "entry_idempotency_claims",
        ["user_id"],
    )
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
        sa.CheckConstraint(
            "retry_count >= 0",
            name="ck_outbox_events_retry_count",
        ),
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
        sa.UniqueConstraint(
            "lease_token",
            name="uq_processing_job_claims_lease_token",
        ),
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

    op.execute("PRAGMA foreign_keys=ON")

    for column_name, column in (
        ("selector_version", sa.Column("selector_version", sa.Integer(), nullable=True)),
        ("selector_seed_hash", sa.Column("selector_seed_hash", sa.String(64), nullable=True)),
        ("logical_slot_key", sa.Column("logical_slot_key", sa.String(100), nullable=True)),
    ):
        if not _column_exists(bind, "personality_messages", column_name):
            op.add_column("personality_messages", column)

    op.execute(
        "UPDATE personality_messages "
        "SET selector_version = COALESCE(selector_version, 1)"
    )
    op.execute(
        "UPDATE personality_messages "
        "SET logical_slot_key = COALESCE(logical_slot_key, 'primary')"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_personality_messages_selector_slot "
        "ON personality_messages(user_id, entry_id, message_type, logical_slot_key, selector_version)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_personality_messages_selector_seed "
        "ON personality_messages(selector_version, selector_seed_hash)"
    )

    for trigger_sql in (
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_quest_user
        BEFORE INSERT ON personality_messages
        WHEN NEW.quest_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM quests WHERE id = NEW.quest_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.quest_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_quest_user_upd
        BEFORE UPDATE OF quest_id, user_id ON personality_messages
        WHEN NEW.quest_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM quests WHERE id = NEW.quest_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.quest_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_entry_user
        BEFORE INSERT ON personality_messages
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.entry_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_entry_user_upd
        BEFORE UPDATE OF entry_id, user_id ON personality_messages
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.entry_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_quests_entry_user
        BEFORE INSERT ON quests
        WHEN NEW.entry_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                THEN RAISE(ABORT, 'quests.entry_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_quests_entry_user_upd
        BEFORE UPDATE OF entry_id, user_id ON quests
        WHEN NEW.entry_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                THEN RAISE(ABORT, 'quests.entry_id must belong to same user')
            END;
        END;
        """,
    ):
        op.execute(trigger_sql)


def downgrade() -> None:
    raise NotImplementedError("Downgrade for MB81 is not supported.")
