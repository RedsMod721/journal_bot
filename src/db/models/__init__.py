"""
ORM model registry for the RPG Life Tracker.

Import order matters: tables with deferred / circular FKs (forgiveness_configs,
story_arcs) must be imported before the models that reference them so that
SQLAlchemy's mapper can resolve all relationships before `configure_mappers()`
is called.

All models are re-exported here so callers can do:
    from src.db.models import User, Skill, Theme, ...
"""

# 1. Forgiveness first — users.forgiveness_config_id points here
from src.db.models.forgiveness import DecaySnapshot, ForgivenessConfig

# 2. Core user
from src.db.models.user import User

# 3. Journal entries
from src.db.models.journal_entry import EntryAttachment, JournalEntry, JournalEntryStructured

# 4. Skills & themes
from src.db.models.skill import Skill, SkillThemeMapping, Theme

# 5. Quests
from src.db.models.quest import Quest, QuestFailureTracker, QuestTemplate

# 6. XP awards (references all of the above)
from src.db.models.xp import XpAward

__all__ = [
    # Forgiveness / decay
    "ForgivenessConfig",
    "DecaySnapshot",
    # User
    "User",
    # Journal
    "JournalEntry",
    "JournalEntryStructured",
    "EntryAttachment",
    # Skills & themes
    "Skill",
    "Theme",
    "SkillThemeMapping",
    # Quests
    "QuestTemplate",
    "Quest",
    "QuestFailureTracker",
    # XP
    "XpAward",
]
