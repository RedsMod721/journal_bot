"""MB78 relax legacy NOT NULL columns that are outside the canonical runtime.

Revision ID: b10000000015
Revises: b10000000014
Create Date: 2026-03-12

Older bootstrap revisions left several legacy columns on core tables with
``NOT NULL`` and no server default. The canonical ``src`` ORM no longer writes
those fields, so inserts fail unless the columns are made optional.

This migration preserves the legacy columns for compatibility but relaxes them
to nullable using table rebuilds on SQLite.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "b10000000015"
down_revision: Union[str, Sequence[str], None] = "b10000000014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _unique_constraints(table_name: str) -> set[str]:
    inspector = inspect(op.get_bind())
    return {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }


def _drop_personality_message_triggers(bind) -> None:
    for trigger_name in (
        "trg_personality_messages_entry_user_upd",
        "trg_personality_messages_entry_user",
        "trg_personality_messages_quest_user_upd",
        "trg_personality_messages_quest_user",
    ):
        bind.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_name}"))


def _create_personality_message_triggers(bind) -> None:
    for stmt in (
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
        WHEN NEW.entry_id IS NOT NULL
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
        WHEN NEW.entry_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.entry_id must belong to same user')
            END;
        END;
        """,
    ):
        bind.execute(sa.text(stmt))


def _relax_users() -> None:
    if "is_active" not in _columns("users"):
        return
    with op.batch_alter_table("users", recreate="always") as batch_op:
        batch_op.alter_column("is_active", existing_type=sa.Boolean(), nullable=True)


def _relax_journal_entries() -> None:
    columns = _columns("journal_entries")
    constraints = _unique_constraints("journal_entries")
    with op.batch_alter_table("journal_entries", recreate="always") as batch_op:
        if "ai_categories" in columns:
            batch_op.alter_column("ai_categories", existing_type=sa.JSON(), nullable=True)
        if "ai_suggested_quests" in columns:
            batch_op.alter_column("ai_suggested_quests", existing_type=sa.JSON(), nullable=True)
        if "ai_processed" in columns:
            batch_op.alter_column("ai_processed", existing_type=sa.Boolean(), nullable=True)
        if "manual_theme_ids" in columns:
            batch_op.alter_column("manual_theme_ids", existing_type=sa.JSON(), nullable=True)
        if "manual_skill_ids" in columns:
            batch_op.alter_column("manual_skill_ids", existing_type=sa.JSON(), nullable=True)
        if "processing_status" in columns:
            batch_op.alter_column("processing_status", existing_type=sa.String(length=20), nullable=True)
        if "retry_count" in columns:
            batch_op.alter_column("retry_count", existing_type=sa.Integer(), nullable=True)
        if "uq_journal_entries_user_id" not in constraints:
            batch_op.create_unique_constraint("uq_journal_entries_user_id", ["user_id", "id"])


def _relax_skills() -> None:
    columns = _columns("skills")
    constraints = _unique_constraints("skills")
    with op.batch_alter_table("skills", recreate="always") as batch_op:
        if "xp_to_next_level" in columns:
            batch_op.alter_column("xp_to_next_level", existing_type=sa.Float(), nullable=True)
        if "practice_time_minutes" in columns:
            batch_op.alter_column("practice_time_minutes", existing_type=sa.Integer(), nullable=True)
        if "difficulty" in columns:
            batch_op.alter_column("difficulty", existing_type=sa.String(length=20), nullable=True)
        if "skill_metadata" in columns:
            batch_op.alter_column("skill_metadata", existing_type=sa.JSON(), nullable=True)
        if "limit_break_progress" in columns:
            batch_op.alter_column("limit_break_progress", existing_type=sa.Integer(), nullable=True)
        if "limit_break_unlocked" in columns:
            batch_op.alter_column("limit_break_unlocked", existing_type=sa.Boolean(), nullable=True)
        if "uq_skills_user_id" not in constraints:
            batch_op.create_unique_constraint("uq_skills_user_id", ["user_id", "id"])


def _relax_themes() -> None:
    columns = _columns("themes")
    constraints = _unique_constraints("themes")
    with op.batch_alter_table("themes", recreate="always") as batch_op:
        if "xp_to_next_level" in columns:
            batch_op.alter_column("xp_to_next_level", existing_type=sa.Float(), nullable=True)
        if "corrosion_level" in columns:
            batch_op.alter_column("corrosion_level", existing_type=sa.String(length=20), nullable=True)
        if "theme_metadata" in columns:
            batch_op.alter_column("theme_metadata", existing_type=sa.JSON(), nullable=True)
        if "uq_themes_user_id" not in constraints:
            batch_op.create_unique_constraint("uq_themes_user_id", ["user_id", "id"])


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    if is_sqlite:
        bind.execute(sa.text("PRAGMA foreign_keys=OFF"))
        _drop_personality_message_triggers(bind)
    try:
        _relax_users()
        _relax_journal_entries()
        _relax_skills()
        _relax_themes()
    finally:
        if is_sqlite:
            _create_personality_message_triggers(bind)
            bind.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    # Forward-only compatibility fix.
    pass
