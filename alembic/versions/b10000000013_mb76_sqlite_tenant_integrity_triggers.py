"""MB76 add SQLite tenant-integrity triggers for personality_messages.

Revision ID: b10000000013
Revises: b10000000012
Create Date: 2026-03-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b10000000013"
down_revision: Union[str, Sequence[str], None] = "b10000000012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    trigger_sql = [
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_quest_user
        BEFORE INSERT ON personality_messages
        WHEN NEW.quest_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM quests WHERE id = NEW.quest_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.quest_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_quest_user_upd
        BEFORE UPDATE OF quest_id, user_id ON personality_messages
        WHEN NEW.quest_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM quests WHERE id = NEW.quest_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.quest_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_entry_user
        BEFORE INSERT ON personality_messages
        WHEN NEW.entry_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.entry_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_entry_user_upd
        BEFORE UPDATE OF entry_id, user_id ON personality_messages
        WHEN NEW.entry_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.entry_id must belong to same user')
            END;
        END;
        """,
    ]

    for stmt in trigger_sql:
        bind.execute(sa.text(stmt))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    for trigger_name in (
        "trg_personality_messages_entry_user_upd",
        "trg_personality_messages_entry_user",
        "trg_personality_messages_quest_user_upd",
        "trg_personality_messages_quest_user",
    ):
        bind.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
