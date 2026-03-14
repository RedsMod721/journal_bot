"""MB85 — Quest Matcher v10 schema (Section 10).

Adds the four deterministic partial unique indexes required by Section 10.0.2,
the two contribution ledger tables (days + entries) for streak idempotency
(Section 10.5.4), missing quest_progress columns, and the new
confidence_threshold_streak field on users.

What already existed (no-ops in this migration):
    - quests table — created in MB20
    - quest_progress table — created in MB20
    - users.learning_phase_complete / quest_decisions_count /
      confidence_threshold_instant / confidence_threshold_longterm — MB00

What this migration adds:
    1. users.confidence_threshold_streak (Float, default 0.55)
    2. Four partial unique indexes on quests (SQLite-safe raw SQL)
    3. quest_progress.required_progress / last_progress_local_date /
       updated_at_utc_ms columns
    4. quest_progress_contribution_days table
    5. quest_progress_contribution_entries table

Revision ID: b10000000022
Revises: b10000000021
Create Date: 2026-03-21 09:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b10000000022"
down_revision: Union[str, Sequence[str], None] = "b10000000021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _columns(bind: sa.engine.Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(bind: sa.engine.Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    names = {index["name"] for index in inspector.get_indexes(table_name)}
    names.update(
        constraint["name"]
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    )
    return names


def _add_column_if_missing(
    bind: sa.engine.Connection, table_name: str, column: sa.Column
) -> None:
    if column.name not in _columns(bind, table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------ #
    # 1. users — add confidence_threshold_streak                          #
    # ------------------------------------------------------------------ #
    _add_column_if_missing(
        bind,
        "users",
        sa.Column(
            "confidence_threshold_streak",
            sa.Float(),
            nullable=False,
            server_default="0.55",
        ),
    )

    # ------------------------------------------------------------------ #
    # 2. quests — four deterministic partial unique indexes (§10.0.2)     #
    # ------------------------------------------------------------------ #
    # SQLite requires raw DDL for partial (WHERE) indexes; PostgreSQL uses
    # the postgresql_where kwarg.  We branch on dialect for portability.
    if bind.dialect.name == "sqlite":
        bind.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_quests_instant_unique"
                " ON quests(user_id, entry_id)"
                " WHERE quest_type = 'instant'"
            )
        )
        bind.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_quests_streak_active_unique"
                " ON quests(user_id, semantic_key)"
                " WHERE quest_type = 'longterm'"
                "   AND completion_type = 'streak'"
                "   AND status = 'active'"
            )
        )
        bind.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_quests_template_instance_unique"
                " ON quests(user_id, template_quest_type, instance_key)"
                " WHERE quest_type = 'longterm'"
                "   AND status = 'active'"
                "   AND completion_type IN ('cumulative', 'recursive')"
            )
        )
        bind.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_quests_recursive_successor_unique"
                " ON quests(user_id, successor_key)"
                " WHERE quest_type = 'longterm'"
                "   AND completion_type = 'recursive'"
            )
        )
    else:
        op.create_index(
            "idx_quests_instant_unique",
            "quests",
            ["user_id", "entry_id"],
            unique=True,
            postgresql_where=sa.text("quest_type = 'instant'"),
        )
        op.create_index(
            "idx_quests_streak_active_unique",
            "quests",
            ["user_id", "semantic_key"],
            unique=True,
            postgresql_where=sa.text(
                "quest_type = 'longterm' AND completion_type = 'streak' AND status = 'active'"
            ),
        )
        op.create_index(
            "idx_quests_template_instance_unique",
            "quests",
            ["user_id", "template_quest_type", "instance_key"],
            unique=True,
            postgresql_where=sa.text(
                "quest_type = 'longterm' AND status = 'active'"
                " AND completion_type IN ('cumulative', 'recursive')"
            ),
        )
        op.create_index(
            "idx_quests_recursive_successor_unique",
            "quests",
            ["user_id", "successor_key"],
            unique=True,
            postgresql_where=sa.text(
                "quest_type = 'longterm' AND completion_type = 'recursive'"
            ),
        )

    # ------------------------------------------------------------------ #
    # 3. quest_progress — add missing Section 10 columns                  #
    # ------------------------------------------------------------------ #
    # Existing columns kept intact: progress_value, streak_current,
    # streak_best, last_progress_date, updated_at
    _add_column_if_missing(
        bind,
        "quest_progress",
        sa.Column("required_progress", sa.Integer(), nullable=False, server_default="1"),
    )
    _add_column_if_missing(
        bind,
        "quest_progress",
        sa.Column("last_progress_local_date", sa.String(10), nullable=True),
    )
    _add_column_if_missing(
        bind,
        "quest_progress",
        sa.Column("updated_at_utc_ms", sa.BigInteger(), nullable=True),
    )

    # ------------------------------------------------------------------ #
    # 4. quest_progress_contribution_days                                 #
    # ------------------------------------------------------------------ #
    if not _table_exists(bind, "quest_progress_contribution_days"):
        op.create_table(
            "quest_progress_contribution_days",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("quest_id", sa.String(36), nullable=False),
            sa.Column("contribution_local_date", sa.String(10), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["user_id", "quest_id"],
                ["quests.user_id", "quests.id"],
                ondelete="CASCADE",
                name="fk_contribution_days_user_quest",
            ),
            sa.UniqueConstraint(
                "user_id",
                "quest_id",
                "contribution_local_date",
                name="uq_contribution_days_user_quest_date",
            ),
        )
    day_indexes = _indexes(bind, "quest_progress_contribution_days")
    if "idx_contribution_days_quest" not in day_indexes:
        op.create_index(
            "idx_contribution_days_quest",
            "quest_progress_contribution_days",
            ["quest_id"],
        )
    if "idx_contribution_days_date" not in day_indexes:
        op.create_index(
            "idx_contribution_days_date",
            "quest_progress_contribution_days",
            ["contribution_local_date"],
        )

    # ------------------------------------------------------------------ #
    # 5. quest_progress_contribution_entries                              #
    # ------------------------------------------------------------------ #
    if not _table_exists(bind, "quest_progress_contribution_entries"):
        op.create_table(
            "quest_progress_contribution_entries",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("quest_id", sa.String(36), nullable=False),
            sa.Column("entry_id", sa.String(36), nullable=False),
            sa.Column("contribution_local_date", sa.String(10), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["user_id", "quest_id"],
                ["quests.user_id", "quests.id"],
                ondelete="CASCADE",
                name="fk_contribution_entries_user_quest",
            ),
            sa.ForeignKeyConstraint(
                ["user_id", "entry_id"],
                ["journal_entries.user_id", "journal_entries.id"],
                ondelete="CASCADE",
                name="fk_contribution_entries_user_entry",
            ),
            sa.UniqueConstraint(
                "user_id",
                "quest_id",
                "entry_id",
                name="uq_contribution_entries_user_quest_entry",
            ),
        )
    entry_indexes = _indexes(bind, "quest_progress_contribution_entries")
    if "idx_contribution_entries_quest" not in entry_indexes:
        op.create_index(
            "idx_contribution_entries_quest",
            "quest_progress_contribution_entries",
            ["quest_id"],
        )
    if "idx_contribution_entries_entry" not in entry_indexes:
        op.create_index(
            "idx_contribution_entries_entry",
            "quest_progress_contribution_entries",
            ["entry_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()

    # 5. Drop contribution_entries
    op.drop_index(
        "idx_contribution_entries_entry",
        table_name="quest_progress_contribution_entries",
    )
    op.drop_index(
        "idx_contribution_entries_quest",
        table_name="quest_progress_contribution_entries",
    )
    op.drop_table("quest_progress_contribution_entries")

    # 4. Drop contribution_days
    op.drop_index(
        "idx_contribution_days_date",
        table_name="quest_progress_contribution_days",
    )
    op.drop_index(
        "idx_contribution_days_quest",
        table_name="quest_progress_contribution_days",
    )
    op.drop_table("quest_progress_contribution_days")

    # 3. Remove quest_progress columns
    op.drop_column("quest_progress", "updated_at_utc_ms")
    op.drop_column("quest_progress", "last_progress_local_date")
    op.drop_column("quest_progress", "required_progress")

    # 2. Drop partial unique indexes on quests
    if bind.dialect.name == "sqlite":
        bind.execute(
            sa.text("DROP INDEX IF EXISTS idx_quests_recursive_successor_unique")
        )
        bind.execute(
            sa.text("DROP INDEX IF EXISTS idx_quests_template_instance_unique")
        )
        bind.execute(
            sa.text("DROP INDEX IF EXISTS idx_quests_streak_active_unique")
        )
        bind.execute(
            sa.text("DROP INDEX IF EXISTS idx_quests_instant_unique")
        )
    else:
        op.drop_index("idx_quests_recursive_successor_unique", table_name="quests")
        op.drop_index("idx_quests_template_instance_unique", table_name="quests")
        op.drop_index("idx_quests_streak_active_unique", table_name="quests")
        op.drop_index("idx_quests_instant_unique", table_name="quests")

    # 1. Remove users column
    op.drop_column("users", "confidence_threshold_streak")
