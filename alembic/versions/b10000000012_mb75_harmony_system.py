"""MB75 — Harmony system pivot schema.

Replaces the EAV harmony_dimensions table (one row per dimension) and the
JSON-blob harmony_snapshots table with pivot-style tables that store all 7
dimension scores as explicit columns on a single row per user/date.

Changes
-------
harmony_dimensions (rebuilt)
    Before: id, user_id, dimension (str), score (float)
    After:  user_id (PK), physical, mental, social, productivity, rest,
            growth, creative, overall_balance, overwork_stage,
            overwork_consecutive_days, overwork_last_evaluated_local_date,
            overwork_last_changed_at_utc, updated_at

harmony_snapshots (rebuilt)
    Before: id, user_id, snapshot_date (str), dimensions_json, overall_score
    After:  id, user_id, snapshot_date (Date), physical, mental, social,
            productivity, rest, growth, creative, overall_balance, created_at

Architecture reference: §6 (Harmony System), §6.3 (Dimension Scoring),
§6.4 (Overwork Detection).

Revision ID: b10000000012
Revises: b10000000011
Create Date: 2026-03-13 10:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "b10000000012"
down_revision: Union[str, Sequence[str], None] = "b10000000011"
branch_labels = None
depends_on = None

_DIM_COLUMNS = (
    "physical",
    "mental",
    "social",
    "productivity",
    "rest",
    "growth",
    "creative",
)


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return table_name in inspector.get_table_names()


def _existing_indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    # ------------------------------------------------------------------
    # harmony_dimensions — drop old EAV table, create pivot table
    # ------------------------------------------------------------------
    if _table_exists("harmony_dimensions"):
        for idx in _existing_indexes("harmony_dimensions"):
            op.drop_index(idx, table_name="harmony_dimensions")
        op.drop_table("harmony_dimensions")

    op.create_table(
        "harmony_dimensions",
        sa.Column("user_id", sa.String(36), nullable=False),
        # 7 dimension scores
        *[
            sa.Column(dim, sa.Float(), nullable=False, server_default="0.5")
            for dim in _DIM_COLUMNS
        ],
        # Overall balance — mean of 7 dimensions
        sa.Column(
            "overall_balance", sa.Float(), nullable=False, server_default="0.5"
        ),
        # Overwork tracking (§6.4)
        sa.Column(
            "overwork_stage", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "overwork_consecutive_days",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "overwork_last_evaluated_local_date", sa.Date(), nullable=True
        ),
        sa.Column(
            "overwork_last_changed_at_utc", sa.DateTime(), nullable=True
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_harmony_dimensions"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_harmony_dimensions_user_id",
        ),
        sa.CheckConstraint(
            "overwork_stage >= 0 AND overwork_stage <= 3",
            name="ck_harmony_dimensions_overwork_stage",
        ),
    )

    op.create_index(
        "idx_harmony_dimensions_user", "harmony_dimensions", ["user_id"]
    )

    # ------------------------------------------------------------------
    # harmony_snapshots — drop old JSON-blob table, create pivot table
    # ------------------------------------------------------------------
    if _table_exists("harmony_snapshots"):
        for idx in _existing_indexes("harmony_snapshots"):
            op.drop_index(idx, table_name="harmony_snapshots")
        op.drop_table("harmony_snapshots")

    op.create_table(
        "harmony_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        # 7 dimension scores at snapshot time
        *[sa.Column(dim, sa.Float(), nullable=False) for dim in _DIM_COLUMNS],
        sa.Column("overall_balance", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_harmony_snapshots"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_harmony_snapshots_user_id",
        ),
        sa.UniqueConstraint(
            "user_id",
            "snapshot_date",
            name="uq_harmony_snapshots_user_date",
        ),
    )

    op.create_index("idx_harmony_snapshots_user", "harmony_snapshots", ["user_id"])
    op.create_index(
        "idx_harmony_snapshots_user_date",
        "harmony_snapshots",
        ["user_id", "snapshot_date"],
    )


def downgrade() -> None:
    # Restore EAV harmony_dimensions
    if _table_exists("harmony_snapshots"):
        for idx in _existing_indexes("harmony_snapshots"):
            op.drop_index(idx, table_name="harmony_snapshots")
        op.drop_table("harmony_snapshots")

    if _table_exists("harmony_dimensions"):
        for idx in _existing_indexes("harmony_dimensions"):
            op.drop_index(idx, table_name="harmony_dimensions")
        op.drop_table("harmony_dimensions")

    op.create_table(
        "harmony_dimensions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_harmony_dimensions_eav"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_harmony_dimensions_eav_user_id",
        ),
        sa.UniqueConstraint(
            "user_id",
            "dimension",
            name="uq_harmony_dimensions_user_dimension",
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 1.0",
            name="ck_harmony_dimensions_score",
        ),
    )
    op.create_index(
        "idx_harmony_dimensions_user", "harmony_dimensions", ["user_id"]
    )

    op.create_table(
        "harmony_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("snapshot_date", sa.String(10), nullable=False),
        sa.Column("dimensions_json", sa.String(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_harmony_snapshots_eav"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_harmony_snapshots_eav_user_id",
        ),
        sa.UniqueConstraint(
            "user_id",
            "snapshot_date",
            name="uq_harmony_snapshots_user_date",
        ),
        sa.CheckConstraint(
            "overall_score >= 0 AND overall_score <= 1.0",
            name="ck_harmony_snapshots_overall",
        ),
    )
    op.create_index("idx_harmony_snapshots_user", "harmony_snapshots", ["user_id"])
    op.create_index(
        "idx_harmony_snapshots_user_date",
        "harmony_snapshots",
        ["user_id", "snapshot_date"],
    )
