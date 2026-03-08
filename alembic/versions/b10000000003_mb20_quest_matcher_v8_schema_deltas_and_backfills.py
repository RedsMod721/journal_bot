"""MB20 quest matcher v8 schema deltas and backfills.

Revision ID: b10000000003
Revises: b10000000002
Create Date: 2026-02-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b10000000003"
down_revision: Union[str, Sequence[str], None] = "b10000000002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Canonical v8 support indexes for quest identity keys.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_quests_template_quest_type ON quests(template_quest_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_quests_semantic_key ON quests(user_id, semantic_key)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_quests_semantic_key")
    op.execute("DROP INDEX IF EXISTS idx_quests_template_quest_type")
