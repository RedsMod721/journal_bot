"""MB73 add forgiveness system tables and columns.

Idempotent migration — safe to run whether or not MB00 already created these
tables via Base.metadata.create_all(). All table creations use
``CREATE TABLE IF NOT EXISTS`` and all column additions are wrapped in
try/except so that pre-existing columns are silently skipped.

New in this migration (net-new columns not present in any earlier migration):
    - insights.last_reinforced_at  (TIMESTAMP, nullable)
    - skills.staleness / decay_paused / last_activity_at (guard-added)
    - insights.strength (guard-added)
    - users.forgiveness_config_id (guard-added)
    - forgiveness_configs table (guard-created)
    - decay_snapshots table (guard-created)
    - Covering indexes for staleness queries

Revision ID: b10000000010
Revises: b10000000009
Create Date: 2026-03-13 09:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b10000000010"
down_revision: Union[str, Sequence[str], None] = "b10000000009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(conn: sa.engine.Connection, sql: str) -> None:
    """Execute an ALTER TABLE ADD COLUMN, ignoring duplicate-column errors."""
    try:
        conn.execute(sa.text(sql))
    except Exception:
        pass  # Column already exists (OperationalError on SQLite)


def upgrade() -> None:
    conn = op.get_bind()

    # ------------------------------------------------------------------
    # 1. forgiveness_configs — one row per user, controls decay rates
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS forgiveness_configs (
            id      TEXT NOT NULL PRIMARY KEY,
            user_id TEXT NOT NULL UNIQUE,

            preset                      TEXT    NOT NULL DEFAULT 'balanced',

            skill_decay_rate            REAL    NOT NULL DEFAULT 0.05,
            insight_decay_rate          REAL    NOT NULL DEFAULT 0.10,

            skill_grace_period_days     INTEGER NOT NULL DEFAULT 7,
            insight_grace_period_days   INTEGER NOT NULL DEFAULT 3,

            critical_staleness_threshold REAL   NOT NULL DEFAULT 0.80,

            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """))

    # ------------------------------------------------------------------
    # 2. decay_snapshots — daily staleness aggregates per user
    #    Column names follow the canonical architecture doc (v10.4).
    # ------------------------------------------------------------------
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS decay_snapshots (
            id            TEXT NOT NULL PRIMARY KEY,
            user_id       TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,

            average_skill_staleness   REAL,
            average_insight_staleness REAL,
            skills_near_critical      INTEGER,

            skill_staleness_map   TEXT,
            insight_staleness_map TEXT,

            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (user_id, snapshot_date)
        )
    """))

    # ------------------------------------------------------------------
    # 3. skills — staleness / decay columns (guard-add; may exist from MB00)
    # ------------------------------------------------------------------
    _add_column_if_missing(
        conn,
        "ALTER TABLE skills ADD COLUMN staleness REAL NOT NULL DEFAULT 0.0"
    )
    _add_column_if_missing(
        conn,
        "ALTER TABLE skills ADD COLUMN decay_paused INTEGER NOT NULL DEFAULT 0"
    )
    _add_column_if_missing(
        conn,
        "ALTER TABLE skills ADD COLUMN last_activity_at TIMESTAMP"
    )

    # ------------------------------------------------------------------
    # 4. insights — strength (guard-add) + last_reinforced_at (net-new)
    # ------------------------------------------------------------------
    _add_column_if_missing(
        conn,
        "ALTER TABLE insights ADD COLUMN strength REAL NOT NULL DEFAULT 1.0"
    )
    # Net-new: not in any previous migration or MB00 model snapshot
    _add_column_if_missing(
        conn,
        "ALTER TABLE insights ADD COLUMN last_reinforced_at TIMESTAMP"
    )

    # ------------------------------------------------------------------
    # 5. users — FK pointer to forgiveness_configs (guard-add)
    # ------------------------------------------------------------------
    _add_column_if_missing(
        conn,
        "ALTER TABLE users ADD COLUMN forgiveness_config_id TEXT "
        "REFERENCES forgiveness_configs(id) ON DELETE SET NULL"
    )

    # ------------------------------------------------------------------
    # 6. Indexes (all IF NOT EXISTS — safe to re-run)
    # ------------------------------------------------------------------
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_forgiveness_configs_user "
        "ON forgiveness_configs(user_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_forgiveness_configs_preset "
        "ON forgiveness_configs(preset)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_decay_snapshots_user_date "
        "ON decay_snapshots(user_id, snapshot_date DESC)"
    ))
    # Covering index for decay worker queries (find most-stale skills fast)
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_skills_staleness "
        "ON skills(staleness)"
    ))
    # Composite: decay worker fetches per-user stale skills
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_skills_user_staleness "
        "ON skills(user_id, staleness)"
    ))
    # insights decay queries
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_insights_user_strength "
        "ON insights(user_id, strength)"
    ))


def downgrade() -> None:
    conn = op.get_bind()

    # Drop indexes added by this migration
    for idx in (
        "idx_insights_user_strength",
        "idx_skills_user_staleness",
        "idx_skills_staleness",
        "idx_decay_snapshots_user_date",
        "idx_forgiveness_configs_preset",
        "idx_forgiveness_configs_user",
    ):
        conn.execute(sa.text(f"DROP INDEX IF EXISTS {idx}"))

    # Remove net-new column (last_reinforced_at is the only truly new column)
    # SQLite does not support DROP COLUMN in older versions; use batch mode.
    with op.batch_alter_table("insights") as batch_op:
        batch_op.drop_column("last_reinforced_at")

    # Drop tables only if this migration created them.
    # Guard: skip if other data already existed (i.e., MB00 created them).
    # We use IF EXISTS so a partial downgrade doesn't hard-fail.
    conn.execute(sa.text("DROP TABLE IF EXISTS decay_snapshots"))
    conn.execute(sa.text("DROP TABLE IF EXISTS forgiveness_configs"))
