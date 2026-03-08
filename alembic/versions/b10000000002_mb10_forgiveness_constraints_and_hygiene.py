"""MB10 forgiveness constraints and hygiene.

Revision ID: b10000000002
Revises: b10000000001
Create Date: 2026-02-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b10000000002"
down_revision: Union[str, Sequence[str], None] = "b10000000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_forgiveness_configs_user_id ON forgiveness_configs(user_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_decay_snapshots_user_snapshot_date ON decay_snapshots(user_id, snapshot_date)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_decay_snapshots_user_snapshot_date")
    op.execute("DROP INDEX IF EXISTS idx_forgiveness_configs_user_id")
