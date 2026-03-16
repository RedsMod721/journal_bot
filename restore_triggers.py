#!/usr/bin/env python
"""Restore SQLite tenant-integrity triggers for personality_messages."""
import sqlite3

conn = sqlite3.connect('data/db/rpg_life_tracker.db')

triggers = [
    """
    CREATE TRIGGER IF NOT EXISTS trg_personality_messages_quest_user
    BEFORE INSERT ON personality_messages
    WHEN NEW.quest_id IS NOT NULL
    BEGIN
        SELECT CASE
            WHEN (SELECT user_id FROM quests WHERE id = NEW.quest_id) != NEW.user_id
            THEN RAISE(ABORT, 'personality_messages.quest_id must belong to same user')
        END;
    END
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
    END
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
    END
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
    END
    """
]

for trigger in triggers:
    try:
        conn.execute(trigger)
        print(f"✓ Created trigger")
    except Exception as e:
        print(f"✗ Error: {e}")

conn.commit()
print("\n✓ All triggers restored")
conn.close()
