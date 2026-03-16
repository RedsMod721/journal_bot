"""Repair personality_messages schema broken by mb91.

Revision ID: b10000000028
Revises: b10000000027
Create Date: 2026-03-16 00:00:00.000000

mb91 (b10000000027) recreated personality_messages with two bugs:
  1. Wrong message_type CHECK values (old 'response'/'guidance'/'summary'/'warning'
     instead of the correct set from the model).
  2. Missing uq_personality_messages_selector_slot unique constraint.
  3. Missing most indexes.

This migration corrects all three issues by fully recreating the table with
the correct schema matching src/db/models/personality.py.
"""

import sqlalchemy as sa
from alembic import op

revision = "b10000000028"
down_revision = "b10000000027"
branch_labels = None
depends_on = None

_CORRECT_MESSAGE_TYPES = (
    "'entry_feedback','quest_complete','level_up','arc_trigger',"
    "'safety_intervention','entry_ack','quest_nudge','report_summary'"
)
_CORRECT_PERSONALITIES = (
    "'observer','therapist','coach','sassy','wargod','raphael','system'"
)


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        bind.execute(sa.text("PRAGMA foreign_keys=OFF"))
        try:
            # 1. Create the replacement table with correct constraints
            bind.execute(sa.text(f"""
                CREATE TABLE personality_messages_new (
                    id VARCHAR(36) NOT NULL,
                    user_id VARCHAR(36) NOT NULL,
                    entry_id VARCHAR(36) NOT NULL,
                    personality VARCHAR(50) NOT NULL,
                    message_type VARCHAR(50) NOT NULL,
                    message_text TEXT NOT NULL,
                    selector_version INTEGER NOT NULL,
                    selector_seed_hash VARCHAR(64),
                    logical_slot_key VARCHAR(100) NOT NULL,
                    context_data TEXT NOT NULL,
                    quest_id VARCHAR(36),
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE (user_id, id),
                    CONSTRAINT uq_personality_messages_selector_slot
                        UNIQUE (user_id, entry_id, message_type, logical_slot_key, selector_version),
                    CONSTRAINT ck_personality_messages_personality
                        CHECK (personality IN ({_CORRECT_PERSONALITIES})),
                    CONSTRAINT ck_personality_messages_message_type
                        CHECK (message_type IN ({_CORRECT_MESSAGE_TYPES})),
                    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY(quest_id) REFERENCES quests (id) ON DELETE SET NULL,
                    FOREIGN KEY(entry_id) REFERENCES journal_entries (id) ON DELETE CASCADE
                )
            """))

            # 2. Copy only rows whose message_type is valid in the new constraint.
            #    Rows with old invalid values ('response','guidance','summary','warning')
            #    are silently dropped (they should never exist in production).
            bind.execute(sa.text(f"""
                INSERT INTO personality_messages_new
                SELECT id, user_id, entry_id, personality, message_type, message_text,
                       selector_version, selector_seed_hash, logical_slot_key, context_data,
                       quest_id, created_at
                FROM personality_messages
                WHERE message_type IN ({_CORRECT_MESSAGE_TYPES})
            """))

            # 3. Swap tables
            bind.execute(sa.text("DROP TABLE personality_messages"))
            bind.execute(sa.text(
                "ALTER TABLE personality_messages_new RENAME TO personality_messages"
            ))

            # 4. Recreate all indexes from the ORM model definition
            bind.execute(sa.text(
                "CREATE INDEX idx_personality_messages_user "
                "ON personality_messages(user_id)"
            ))
            bind.execute(sa.text(
                "CREATE INDEX idx_personality_messages_entry "
                "ON personality_messages(entry_id)"
            ))
            bind.execute(sa.text(
                "CREATE INDEX idx_personality_messages_user_entry "
                "ON personality_messages(user_id, entry_id)"
            ))
            bind.execute(sa.text(
                "CREATE INDEX idx_personality_messages_user_entry_type "
                "ON personality_messages(user_id, entry_id, message_type)"
            ))
            bind.execute(sa.text(
                "CREATE INDEX idx_personality_messages_selector_seed "
                "ON personality_messages(user_id, selector_seed_hash)"
            ))

            # 5. Recreate tenant-integrity triggers (IF NOT EXISTS — replay-safe)
            bind.execute(sa.text("""
                CREATE TRIGGER IF NOT EXISTS trg_personality_messages_quest_user
                BEFORE INSERT ON personality_messages
                WHEN NEW.quest_id IS NOT NULL
                BEGIN
                    SELECT CASE
                        WHEN (SELECT user_id FROM quests WHERE id = NEW.quest_id) != NEW.user_id
                        THEN RAISE(ABORT, 'personality_messages.quest_id must belong to same user')
                    END;
                END
            """))
            bind.execute(sa.text("""
                CREATE TRIGGER IF NOT EXISTS trg_personality_messages_quest_user_upd
                BEFORE UPDATE OF quest_id, user_id ON personality_messages
                WHEN NEW.quest_id IS NOT NULL
                BEGIN
                    SELECT CASE
                        WHEN (SELECT user_id FROM quests WHERE id = NEW.quest_id) != NEW.user_id
                        THEN RAISE(ABORT, 'personality_messages.quest_id must belong to same user')
                    END;
                END
            """))
            bind.execute(sa.text("""
                CREATE TRIGGER IF NOT EXISTS trg_personality_messages_entry_user
                BEFORE INSERT ON personality_messages
                WHEN NEW.entry_id IS NOT NULL
                BEGIN
                    SELECT CASE
                        WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                        THEN RAISE(ABORT, 'personality_messages.entry_id must belong to same user')
                    END;
                END
            """))
            bind.execute(sa.text("""
                CREATE TRIGGER IF NOT EXISTS trg_personality_messages_entry_user_upd
                BEFORE UPDATE OF entry_id, user_id ON personality_messages
                WHEN NEW.entry_id IS NOT NULL
                BEGIN
                    SELECT CASE
                        WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                        THEN RAISE(ABORT, 'personality_messages.entry_id must belong to same user')
                    END;
                END
            """))
        finally:
            bind.execute(sa.text("PRAGMA foreign_keys=ON"))
    else:
        # PostgreSQL / other: surgical ALTER only
        with op.batch_alter_table("personality_messages", schema=None) as batch_op:
            batch_op.drop_constraint(
                "ck_personality_messages_message_type", type_="check"
            )
            batch_op.create_check_constraint(
                "ck_personality_messages_message_type",
                f"message_type IN ({_CORRECT_MESSAGE_TYPES})",
            )
            batch_op.create_unique_constraint(
                "uq_personality_messages_selector_slot",
                ["user_id", "entry_id", "message_type", "logical_slot_key", "selector_version"],
            )
            batch_op.create_index("idx_personality_messages_user", ["user_id"])
            batch_op.create_index("idx_personality_messages_entry", ["entry_id"])
            batch_op.create_index(
                "idx_personality_messages_user_entry", ["user_id", "entry_id"]
            )
            batch_op.create_index(
                "idx_personality_messages_user_entry_type",
                ["user_id", "entry_id", "message_type"],
            )
            batch_op.create_index(
                "idx_personality_messages_selector_seed",
                ["user_id", "selector_seed_hash"],
            )


def downgrade() -> None:
    # Restoring to the broken mb91 state is not useful — just note this is irreversible.
    pass
