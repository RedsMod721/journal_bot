"""MB40 Section 12 distributed claims and nodes.

Revision ID: b10000000005
Revises: b10000000004
Create Date: 2026-02-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b10000000005"
down_revision: Union[str, Sequence[str], None] = "b10000000004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_node_task_assignments_task_attempt ON node_task_assignments(task_id, attempt_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_node_task_results_task_attempt ON node_task_results(task_id, attempt_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_node_task_results_task_attempt")
    op.execute("DROP INDEX IF EXISTS uq_node_task_assignments_task_attempt")
