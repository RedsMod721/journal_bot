"""MB50/MB60 metadata and post-migration verification hooks.

Revision ID: b10000000006
Revises: b10000000005
Create Date: 2026-02-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b10000000006"
down_revision: Union[str, Sequence[str], None] = "b10000000005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_personality_msgs_selector_seed ON personality_messages(user_id, selector_seed_hash)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_personality_msgs_selector_seed")
