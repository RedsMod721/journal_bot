"""MB74 add strategy_tracking table.

Idempotent migration — safe to run on databases where the table was already
created via Base.metadata.create_all().  All table / index creations are
wrapped in existence checks so re-running is a no-op.

New in this migration:
    - strategy_tracking table (pivot model — one row per user)
        Stores rolling 30-day per-strategy usage counts, computed variety
        metrics, rolling window dates, and per-strategy streak state for
        diminishing returns (architecture §2 table 31, §5.2–5.3).

Architecture reference: §2 (table 31), §5.2 (Six Balance Strategies),
§5.3 (Variety Score), §5.9 (Diminishing Returns).

Revision ID: b10000000011
Revises: b10000000010
Create Date: 2026-03-13 09:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "b10000000011"
down_revision: Union[str, Sequence[str], None] = "b10000000010"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return table_name in inspector.get_table_names()


def _existing_indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    required_columns = {
        "id",
        "user_id",
        "social_risk_count",
        "study_burst_count",
        "mundane_focus_count",
        "troll_exploits_count",
        "daily_grind_count",
        "harmony_balance_count",
        "strategy_streaks_json",
        "variety_score",
        "variety_bonus_pct",
        "window_start_date",
        "window_end_date",
        "created_at",
        "updated_at",
    }

    if _table_exists("strategy_tracking"):
        existing_columns = _existing_columns("strategy_tracking")
        if not required_columns.issubset(existing_columns):
            for idx in _existing_indexes("strategy_tracking"):
                op.drop_index(idx, table_name="strategy_tracking")
            op.drop_table("strategy_tracking")

    if not _table_exists("strategy_tracking"):
        op.create_table(
            "strategy_tracking",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("user_id", sa.String(36), nullable=False),
            # Rolling 30-day strategy counts
            sa.Column(
                "social_risk_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "study_burst_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "mundane_focus_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "troll_exploits_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "daily_grind_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "harmony_balance_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            # Diminishing-returns streak state
            # JSON: {strategy_key: {count: int, last_day: "YYYY-MM-DD"}}
            sa.Column(
                "strategy_streaks_json",
                sa.String(),
                nullable=False,
                server_default="{}",
            ),
            # Computed variety metrics (§5.3)
            sa.Column("variety_score", sa.Float(), nullable=True),
            sa.Column("variety_bonus_pct", sa.Float(), nullable=True),
            # Rolling window boundaries (§5.0.4)
            sa.Column("window_start_date", sa.Date(), nullable=True),
            sa.Column("window_end_date", sa.Date(), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_strategy_tracking"),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                ondelete="CASCADE",
                name="fk_strategy_tracking_user_id",
            ),
            sa.UniqueConstraint("user_id", name="uq_strategy_tracking_user_id"),
            sa.CheckConstraint(
                "social_risk_count >= 0",
                name="ck_strategy_tracking_social_risk_count",
            ),
            sa.CheckConstraint(
                "study_burst_count >= 0",
                name="ck_strategy_tracking_study_burst_count",
            ),
            sa.CheckConstraint(
                "mundane_focus_count >= 0",
                name="ck_strategy_tracking_mundane_focus_count",
            ),
            sa.CheckConstraint(
                "troll_exploits_count >= 0",
                name="ck_strategy_tracking_troll_exploits_count",
            ),
            sa.CheckConstraint(
                "daily_grind_count >= 0",
                name="ck_strategy_tracking_daily_grind_count",
            ),
            sa.CheckConstraint(
                "harmony_balance_count >= 0",
                name="ck_strategy_tracking_harmony_balance_count",
            ),
            sa.CheckConstraint(
                "variety_score IS NULL OR (variety_score >= 0 AND variety_score <= 1.0)",
                name="ck_strategy_tracking_variety_score",
            ),
            sa.CheckConstraint(
                "variety_bonus_pct IS NULL OR"
                " (variety_bonus_pct >= 0 AND variety_bonus_pct <= 0.60)",
                name="ck_strategy_tracking_variety_bonus_pct",
            ),
        )

    existing = _existing_indexes("strategy_tracking")

    if "idx_strategy_tracking_user" not in existing:
        op.create_index(
            "idx_strategy_tracking_user",
            "strategy_tracking",
            ["user_id"],
        )

    if "idx_strategy_tracking_window" not in existing:
        op.create_index(
            "idx_strategy_tracking_window",
            "strategy_tracking",
            ["window_end_date"],
        )


def downgrade() -> None:
    if _table_exists("strategy_tracking"):
        existing = _existing_indexes("strategy_tracking")
        for idx in ("idx_strategy_tracking_window", "idx_strategy_tracking_user"):
            if idx in existing:
                op.drop_index(idx, table_name="strategy_tracking")
        op.drop_table("strategy_tracking")
