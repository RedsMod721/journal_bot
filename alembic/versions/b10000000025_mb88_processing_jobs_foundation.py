"""MB88 — Processing jobs foundation: verify & repair canonical schema.

Revision ID: b10000000025
Revises: b10000000024
Create Date: 2026-03-23 10:00:00.000000

All three processing-job tables (processing_jobs, processing_job_attempts,
processing_job_claims) were first created in MB81 and canonicalized in MB82.
This migration is an idempotent guard: it creates them from scratch on fresh
databases and ensures the canonical column set / constraints exist on any DB
that passed through earlier migrations.

Safe to run repeatedly — every DDL step is preceded by an existence check.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision = "b10000000025"
down_revision = "b10000000024"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_exists(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def _column_exists(bind, table: str, column: str) -> bool:
    if not _table_exists(bind, table):
        return False
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def _index_exists(bind, index: str) -> bool:
    for table in sa.inspect(bind).get_table_names():
        if any(i["name"] == index for i in sa.inspect(bind).get_indexes(table)):
            return True
    return False


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    bind = op.get_bind()

    logger.info("[MB88] Starting processing-jobs foundation migration")

    op.execute("PRAGMA foreign_keys=OFF")

    # -----------------------------------------------------------------------
    # processing_jobs
    # -----------------------------------------------------------------------
    if not _table_exists(bind, "processing_jobs"):
        logger.info("[MB88] Creating processing_jobs table from scratch")
        op.create_table(
            "processing_jobs",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("entry_id", sa.String(36), nullable=False),
            sa.Column("step_name", sa.String(64), nullable=False),
            sa.Column("processing_run_id", sa.String(36), nullable=False),
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="in_progress",
            ),
            sa.Column("finalized_at", sa.DateTime(), nullable=True),
            sa.Column(
                "attempt_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
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
        logger.info("[MB88] processing_jobs created")
    else:
        logger.info("[MB88] processing_jobs already exists — verifying columns")
        # Ensure optional columns added after MB81 exist
        for col_name, col_def in (
            ("result_json", sa.Column("result_json", sa.Text(), nullable=True)),
            ("request_payload_hash", sa.Column("request_payload_hash", sa.String(64), nullable=True)),
            ("pipeline_version", sa.Column("pipeline_version", sa.String(50), nullable=True)),
            ("ruleset_version", sa.Column("ruleset_version", sa.String(50), nullable=True)),
            ("config_version", sa.Column("config_version", sa.String(50), nullable=True)),
            ("ai_version_snapshot", sa.Column("ai_version_snapshot", sa.Text(), nullable=True)),
            ("prompt_version_snapshot", sa.Column("prompt_version_snapshot", sa.Text(), nullable=True)),
        ):
            if not _column_exists(bind, "processing_jobs", col_name):
                logger.info("[MB88] Adding missing column processing_jobs.%s", col_name)
                op.add_column("processing_jobs", col_def)

    # Indexes — safe because we use raw DDL with IF NOT EXISTS
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_processing_jobs_job "
        "ON processing_jobs(user_id, entry_id, step_name)",
        "CREATE INDEX IF NOT EXISTS idx_processing_jobs_run "
        "ON processing_jobs(user_id, processing_run_id)",
        "CREATE INDEX IF NOT EXISTS idx_processing_jobs_status_updated "
        "ON processing_jobs(status, updated_at)",
        "CREATE INDEX IF NOT EXISTS idx_processing_jobs_entry_pipeline "
        "ON processing_jobs(user_id, entry_id, step_name, status) "
        "WHERE step_name = 'entry_pipeline'",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_processing_jobs_one_success "
        "ON processing_jobs(user_id, entry_id, step_name) "
        "WHERE status = 'succeeded'",
    ):
        op.execute(idx_sql)

    # updated_at trigger — idempotent via IF NOT EXISTS
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_processing_jobs_updated_at
        AFTER UPDATE ON processing_jobs
        FOR EACH ROW
        BEGIN
          UPDATE processing_jobs
          SET updated_at = (datetime('now'))
          WHERE id = NEW.id;
        END;
        """
    )

    # -----------------------------------------------------------------------
    # processing_job_attempts
    # -----------------------------------------------------------------------
    if not _table_exists(bind, "processing_job_attempts"):
        logger.info("[MB88] Creating processing_job_attempts table from scratch")
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
            sa.CheckConstraint(
                "attempt_id >= 1",
                name="ck_processing_job_attempts_attempt_id",
            ),
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
        logger.info("[MB88] processing_job_attempts created")
    else:
        logger.info("[MB88] processing_job_attempts already exists — verifying columns")
        # MB81 used `attempt_number`; MB82 renamed it to `attempt_id`.
        # If a DB has `attempt_number` but not `attempt_id`, we need a rebuild.
        has_attempt_id = _column_exists(bind, "processing_job_attempts", "attempt_id")
        has_executor_type = _column_exists(bind, "processing_job_attempts", "executor_type")
        if not has_attempt_id or not has_executor_type:
            logger.warning(
                "[MB88] processing_job_attempts has pre-MB82 schema "
                "(attempt_id=%s, executor_type=%s) — rebuilding",
                has_attempt_id,
                has_executor_type,
            )
            op.drop_table("processing_job_attempts")
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
                sa.CheckConstraint(
                    "attempt_id >= 1",
                    name="ck_processing_job_attempts_attempt_id",
                ),
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
            logger.info("[MB88] processing_job_attempts rebuilt with canonical schema")

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_processing_job_attempts_job "
        "ON processing_job_attempts(processing_job_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_processing_job_attempts_time "
        "ON processing_job_attempts(attempted_at)"
    )

    # -----------------------------------------------------------------------
    # processing_job_claims
    # -----------------------------------------------------------------------
    if not _table_exists(bind, "processing_job_claims"):
        logger.info("[MB88] Creating processing_job_claims table from scratch")
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
            sa.UniqueConstraint(
                "lease_token",
                name="uq_processing_job_claims_lease_token",
            ),
            sa.CheckConstraint(
                "owner_kind IN ('server_worker','scheduler','admin_recovery')",
                name="ck_processing_job_claims_owner_kind",
            ),
        )
        logger.info("[MB88] processing_job_claims created")
    else:
        logger.info("[MB88] processing_job_claims already exists — no action needed")

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_processing_job_claims_lease_expiry "
        "ON processing_job_claims(lease_expires_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_processing_job_claims_owner "
        "ON processing_job_claims(owner_kind, owner_id)"
    )

    op.execute("PRAGMA foreign_keys=ON")
    logger.info("[MB88] Processing-jobs foundation migration complete")


def downgrade() -> None:
    raise NotImplementedError("Downgrade for MB88 is not supported.")
