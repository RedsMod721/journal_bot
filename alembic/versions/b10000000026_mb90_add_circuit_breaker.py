"""Add circuit breaker state table (Section 11.1.3).

Revision ID: b10000000026
Revises: b10000000025
Create Date: 2026-03-15 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b10000000026"
down_revision = "b10000000025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "circuit_breaker_state",
        sa.Column("scope_key", sa.String(100), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_failure_at", sa.TIMESTAMP, nullable=True),
        sa.Column("last_success_at", sa.TIMESTAMP, nullable=True),
        sa.Column("opened_at", sa.TIMESTAMP, nullable=True),
        sa.Column("half_opened_at", sa.TIMESTAMP, nullable=True),
        sa.Column("next_attempt_at", sa.TIMESTAMP, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP, nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("scope_key"),
        sa.CheckConstraint(
            "state IN ('CLOSED', 'OPEN', 'HALF_OPEN')", name="ck_breaker_state"
        ),
    )
    op.create_index(
        "idx_circuit_breaker_state_state", "circuit_breaker_state", ["state"]
    )
    op.create_index(
        "idx_circuit_breaker_state_next_attempt",
        "circuit_breaker_state",
        ["next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_circuit_breaker_state_next_attempt", "circuit_breaker_state")
    op.drop_index("idx_circuit_breaker_state_state", "circuit_breaker_state")
    op.drop_table("circuit_breaker_state")
