"""MB86 — Section 10.6 XP distribution audit columns.

Adds three columns to xp_awards that the QuestXPDistributionService
(src/core/quest_xp_distribution.py) writes on every award:

    skill_weight_bp       Integer  — award weight in basis points (mirrors
                                     the existing skill_weight Float column)
    quest_matcher_version Integer  — matcher schema version for audit trail
    awarded_at_utc_ms     Integer  — epoch-ms timestamp (parallel to awarded_at;
                                     Section 10 epoch-ms convention)

No new tables or indexes; the existing uq_xp_awards_identity partial unique
constraint (user_id + award_identity_key) continues to provide idempotency.

Revision ID: b10000000023
Revises: b10000000022
Create Date: 2026-03-14 09:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b10000000023"
down_revision: Union[str, Sequence[str], None] = "b10000000022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind: sa.engine.Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(
    bind: sa.engine.Connection, table_name: str, column: sa.Column
) -> None:
    if column.name not in _columns(bind, table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    # skill_weight_bp — integer basis-point counterpart of skill_weight (Float)
    _add_column_if_missing(
        bind,
        "xp_awards",
        sa.Column("skill_weight_bp", sa.Integer(), nullable=True),
    )

    # quest_matcher_version — which matcher schema produced this award
    _add_column_if_missing(
        bind,
        "xp_awards",
        sa.Column("quest_matcher_version", sa.Integer(), nullable=True),
    )

    # awarded_at_utc_ms — epoch-ms twin of awarded_at for Section 10 consumers
    _add_column_if_missing(
        bind,
        "xp_awards",
        sa.Column("awarded_at_utc_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("xp_awards", "awarded_at_utc_ms")
    op.drop_column("xp_awards", "quest_matcher_version")
    op.drop_column("xp_awards", "skill_weight_bp")
