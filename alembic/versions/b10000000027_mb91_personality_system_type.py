"""Add 'system' to personality_messages personality CHECK constraint.

Revision ID: b10000000027
Revises: b10000000026
Create Date: 2026-03-16 00:00:00.000000

Allows personality='system' in personality_messages for deterministic
pipeline system reports (message_type='report_summary').
"""

from alembic import op
import sqlalchemy as sa

revision = "b10000000027"
down_revision = "b10000000026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Modify personality CHECK constraint on personality_messages.
    Uses raw SQL for SQLite to avoid reflection errors on dangling FK references.
    """
    bind = op.get_bind()
    
    if bind.dialect.name == "sqlite":
        # SQLite: recreate table with new constraint (raw SQL to avoid reflection)
        bind.execute(sa.text("PRAGMA foreign_keys=OFF"))
        try:
            bind.execute(sa.text("""
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
                    CONSTRAINT ck_personality_messages_personality 
                        CHECK (personality IN ('observer','therapist','coach','sassy','wargod','raphael','system')),
                    CONSTRAINT ck_personality_messages_message_type 
                        CHECK (message_type IN ('response','guidance','summary','warning','report_summary','entry_feedback')),
                    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY(quest_id) REFERENCES quests (id) ON DELETE SET NULL,
                    FOREIGN KEY(entry_id) REFERENCES journal_entries (id) ON DELETE CASCADE
                )
            """))
            
            # Copy data from old to new
            bind.execute(sa.text("""
                INSERT INTO personality_messages_new
                (id, user_id, entry_id, personality, message_type, message_text, 
                 selector_version, selector_seed_hash, logical_slot_key, context_data, quest_id, created_at)
                SELECT id, user_id, entry_id, personality, message_type, message_text,
                       selector_version, selector_seed_hash, logical_slot_key, context_data, quest_id, created_at
                FROM personality_messages
            """))
            
            # Drop old table and rename
            bind.execute(sa.text("DROP TABLE personality_messages"))
            bind.execute(sa.text("ALTER TABLE personality_messages_new RENAME TO personality_messages"))
            
            # Recreate indexes
            bind.execute(sa.text("""
                CREATE INDEX IF NOT EXISTS idx_personality_msgs_selector_seed 
                ON personality_messages(user_id, selector_seed_hash)
            """))
            
            # Recreate the tenant-integrity triggers
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
        # PostgreSQL / other: use batch_alter_table
        with op.batch_alter_table("personality_messages", schema=None) as batch_op:
            batch_op.drop_constraint(
                "ck_personality_messages_personality", type_="check"
            )
            batch_op.create_check_constraint(
                "ck_personality_messages_personality",
                "personality IN ('observer','therapist','coach','sassy','wargod','raphael','system')",
            )


def downgrade() -> None:
    with op.batch_alter_table("personality_messages", schema=None) as batch_op:
        batch_op.drop_constraint(
            "ck_personality_messages_personality", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_personality_messages_personality",
            "personality IN ('observer','therapist','coach','sassy','wargod','raphael')",
        )
