"""MB30 Section 13 pipeline schema dependencies.

Revision ID: b10000000004
Revises: b10000000003
Create Date: 2026-02-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b10000000004"
down_revision: Union[str, Sequence[str], None] = "b10000000003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_entry_claims_user_key ON entry_idempotency_claims(user_id, idempotency_key)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_outbox_events_dedupe ON outbox_events(event_dedupe_key)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_outbox_events_dedupe")
    op.execute("DROP INDEX IF EXISTS uq_entry_claims_user_key")
