"""MB77 runtime schema compatibility backfills for canonical src models.

Revision ID: b10000000014
Revises: b10000000013
Create Date: 2026-03-12

This migration closes the gap between the old pre-canonical bootstrap chain and
the current ``src.db.models`` runtime expectations. Earlier revisions created
core tables before the canonical column set existed, which leaves fresh
Alembic-built databases missing fields now required by the Week 4/5 runtime.

The migration is intentionally additive and idempotent:
- add missing columns only
- backfill safe defaults for existing rows
- add read/query indexes only when absent

It does not drop legacy columns; those do not block the canonical runtime.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "b10000000014"
down_revision: Union[str, Sequence[str], None] = "b10000000013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _create_index_if_missing(
    name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def _repair_users() -> None:
    bind = op.get_bind()

    _add_column_if_missing(
        "users",
        sa.Column(
            "password_hash",
            sa.String(length=255),
            nullable=False,
            server_default=sa.text("'legacy-unset'"),
        ),
    )
    _add_column_if_missing(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing("users", sa.Column("display_name", sa.String(length=100), nullable=True))
    _add_column_if_missing(
        "users",
        sa.Column("timezone", sa.String(length=50), nullable=False, server_default=sa.text("'UTC'")),
    )
    _add_column_if_missing(
        "users",
        sa.Column("language", sa.String(length=10), nullable=False, server_default=sa.text("'en'")),
    )
    _add_column_if_missing(
        "users",
        sa.Column("home_country", sa.String(length=2), nullable=False, server_default=sa.text("'FR'")),
    )
    _add_column_if_missing(
        "users",
        sa.Column(
            "allow_ip_geolocation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing("users", sa.Column("last_known_country", sa.String(length=2), nullable=True))
    _add_column_if_missing("users", sa.Column("country_last_resolved_at", sa.DateTime(), nullable=True))
    _add_column_if_missing(
        "users",
        sa.Column(
            "learning_phase_complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        "users",
        sa.Column(
            "quest_decisions_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        "users",
        sa.Column(
            "confidence_threshold_instant",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.65"),
        ),
    )
    _add_column_if_missing(
        "users",
        sa.Column(
            "confidence_threshold_longterm",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.45"),
        ),
    )
    _add_column_if_missing("users", sa.Column("active_arc_id", sa.String(length=36), nullable=True))
    _add_column_if_missing(
        "users",
        sa.Column(
            "current_personality",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'observer'"),
        ),
    )
    _add_column_if_missing(
        "users",
        sa.Column(
            "allow_trusted_nodes",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing(
        "users",
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    _add_column_if_missing("users", sa.Column("banned_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("users", sa.Column("ban_reason", sa.String(length=500), nullable=True))
    _add_column_if_missing("users", sa.Column("updated_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))

    bind.execute(
        sa.text(
            """
            UPDATE users
            SET display_name = COALESCE(display_name, username),
                updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
            """
        )
    )

    _create_index_if_missing("idx_users_created", "users", ["created_at"])


def _repair_journal_entries() -> None:
    bind = op.get_bind()
    existing = _columns("journal_entries")

    _add_column_if_missing(
        "journal_entries",
        sa.Column("status", sa.String(length=30), nullable=False, server_default=sa.text("'pending'")),
    )
    _add_column_if_missing(
        "journal_entries",
        sa.Column(
            "question_state",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
    )
    _add_column_if_missing("journal_entries", sa.Column("questions_asked", sa.Text(), nullable=True))
    _add_column_if_missing("journal_entries", sa.Column("question_timeout", sa.DateTime(), nullable=True))
    _add_column_if_missing("journal_entries", sa.Column("recorded_at", sa.DateTime(), nullable=True))
    _add_column_if_missing(
        "journal_entries",
        sa.Column("transcription_confidence", sa.Float(), nullable=True),
    )
    _add_column_if_missing(
        "journal_entries",
        sa.Column("processing_duration_ms", sa.Integer(), nullable=True),
    )
    _add_column_if_missing("journal_entries", sa.Column("error_message", sa.Text(), nullable=True))
    _add_column_if_missing("journal_entries", sa.Column("updated_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("journal_entries", sa.Column("processed_at", sa.DateTime(), nullable=True))

    if "processing_status" in existing:
        bind.execute(
            sa.text(
                """
                UPDATE journal_entries
                SET status = CASE
                    WHEN processing_status = 'processing' THEN 'processing'
                    WHEN processing_status IN ('failed', 'error') THEN 'failed'
                    WHEN processing_status IN ('completed', 'done', 'success') THEN 'completed'
                    ELSE status
                END
                """
            )
        )
    if "processing_error" in existing:
        bind.execute(
            sa.text(
                """
                UPDATE journal_entries
                SET status = 'failed',
                    error_message = COALESCE(error_message, processing_error)
                WHERE processing_error IS NOT NULL AND TRIM(processing_error) != ''
                """
            )
        )
    if "ai_processed" in existing:
        bind.execute(
            sa.text(
                """
                UPDATE journal_entries
                SET status = 'completed'
                WHERE ai_processed = 1 AND status = 'pending'
                """
            )
        )

    bind.execute(
        sa.text(
            """
            UPDATE journal_entries
            SET question_state = COALESCE(question_state, 'none'),
                updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP),
                processed_at = CASE
                    WHEN processed_at IS NULL AND status = 'completed' THEN created_at
                    ELSE processed_at
                END
            """
        )
    )

    _create_index_if_missing("idx_entries_user", "journal_entries", ["user_id"])
    _create_index_if_missing("idx_entries_user_created", "journal_entries", ["user_id", "created_at"])
    _create_index_if_missing("idx_entries_user_status", "journal_entries", ["user_id", "status"])
    _create_index_if_missing("idx_entries_created", "journal_entries", ["created_at"])


def _repair_skills() -> None:
    bind = op.get_bind()

    _add_column_if_missing(
        "skills",
        sa.Column(
            "canonical_name",
            sa.String(length=100),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    _add_column_if_missing("skills", sa.Column("branch_unlocked_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("skills", sa.Column("created_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("skills", sa.Column("global_skill_id", sa.String(length=36), nullable=True))
    _add_column_if_missing(
        "skills",
        sa.Column(
            "is_specialist_track",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    _add_column_if_missing("skills", sa.Column("updated_at", sa.DateTime(), nullable=True))

    bind.execute(
        sa.text(
            """
            UPDATE skills
            SET canonical_name = CASE
                    WHEN canonical_name IS NULL OR TRIM(canonical_name) = '' THEN LOWER(TRIM(name))
                    ELSE canonical_name
                END,
                created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
                updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
            """
        )
    )

    _create_index_if_missing("idx_skills_user", "skills", ["user_id"])
    _create_index_if_missing("idx_skills_user_level", "skills", ["user_id", "level"])
    _create_index_if_missing("idx_skills_user_rank", "skills", ["user_id", "rank"])
    _create_index_if_missing("idx_skills_user_canonical", "skills", ["user_id", "canonical_name"])
    _create_index_if_missing("idx_skills_last_activity", "skills", ["user_id", "last_activity_at"])


def _repair_themes() -> None:
    bind = op.get_bind()

    _add_column_if_missing(
        "themes",
        sa.Column("rank", sa.String(length=3), nullable=False, server_default=sa.text("'F'")),
    )
    _add_column_if_missing("themes", sa.Column("created_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("themes", sa.Column("updated_at", sa.DateTime(), nullable=True))

    bind.execute(
        sa.text(
            """
            UPDATE themes
            SET rank = CASE
                    WHEN level < 10 THEN 'F'
                    WHEN level < 20 THEN 'E'
                    WHEN level < 30 THEN 'D'
                    WHEN level < 40 THEN 'C'
                    WHEN level < 50 THEN 'B'
                    WHEN level < 60 THEN 'A'
                    WHEN level < 75 THEN 'S'
                    WHEN level < 100 THEN 'SS'
                    ELSE 'SSS'
                END,
                created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
                updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
            """
        )
    )

    _create_index_if_missing("idx_themes_user", "themes", ["user_id"])
    _create_index_if_missing("idx_themes_user_level", "themes", ["user_id", "level"])


def upgrade() -> None:
    _repair_users()
    _repair_journal_entries()
    _repair_skills()
    _repair_themes()


def downgrade() -> None:
    # Forward-only compatibility backfill. Older schemas may retain these
    # additive columns safely, and dropping them on SQLite would require table
    # rebuilds that are not justified for rollback.
    pass
