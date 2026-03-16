"""
ORM model registry for the RPG Life Tracker.

Import order matters: tables with deferred / circular FKs (forgiveness_configs,
story_arcs) must be imported before the models that reference them so that
SQLAlchemy's mapper can resolve all relationships before `configure_mappers()`
is called.

All models are re-exported here so callers can do:
    from src.db.models import User, Skill, Theme, ...
"""

# 1. Global/reference tables used by early FKs
from src.db.models.global_kb import (
    GlobalInsight,
    GlobalQuest,
    GlobalSkill,
    KbContribution,
)
from src.db.models.auth import RefreshToken, Role, UserRole
from src.db.models.server_config import ServerConfig
from src.db.models.nodes import (
    NodeAuditLog,
    NodeTaskAssignment,
    NodeTaskResult,
    NodeToken,
    TrustedNode,
)

# 2. Forgiveness first — users.forgiveness_config_id points here
from src.db.models.forgiveness import DecaySnapshot, ForgivenessConfig

# 3. Core user
from src.db.models.user import User

# 4. Journal entries
from src.db.models.journal_entry import (
    EntryAttachment,
    JournalEntry,
    JournalEntryStructured,
)

# 5. Skills & themes
from src.db.models.skill import Skill, SkillThemeMapping, Theme
from src.db.models.user_skill_state import UserSkillState

# 6. Quests
from src.db.models.quest import Quest, QuestFailureTracker, QuestTemplate
from src.db.models.quest_progress import (
    QuestContributionDay,
    QuestContributionEntry,
    QuestProgress,
)
from src.db.models.learning import UserQuestBias, UserQuestPreference

# 7. Story, personality, AI memory
from src.db.models.story import ArcTrigger, StoryArc
from src.db.models.personality import (
    PersonalityMemory,
    PersonalityMessage,
    PersonalityState,
)
from src.db.models.rag import RagDocument

# 8. Progression, analytics, insight systems
from src.db.models.xp import XpAward
from src.db.models.progression import LevelUp
from src.db.models.analytics import UserAnalytics
from src.db.models.harmony import HarmonyDimension, HarmonySnapshot
from src.db.models.insight import Insight, InsightEvidence, Pattern
from src.db.models.strategy import StrategyTracking
from src.db.models.anomaly import AnomalyScore

# 9. Leisure
from src.db.models.leisure import LeisureBudget, SubstanceLimit, SubstanceUsageLog

# 10. Circuit breaker
from src.db.models.circuit_breaker import CircuitBreakerState

# 11. Processing/idempotency/distributed execution
from src.db.models.processing import (
    EntryIdempotencyClaim,
    OutboxEvent,
    ProcessingJob,
    ProcessingJobAttempt,
)
from src.db.models.processing_distributed import ProcessingJobClaim

__all__ = [
    # Global KB
    "GlobalSkill",
    "GlobalQuest",
    "GlobalInsight",
    "KbContribution",
    # Auth / config
    "Role",
    "UserRole",
    "RefreshToken",
    "ServerConfig",
    # Nodes
    "TrustedNode",
    "NodeToken",
    "NodeTaskAssignment",
    "NodeTaskResult",
    "NodeAuditLog",
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
    "UserSkillState",
    # Quests
    "QuestTemplate",
    "Quest",
    "QuestFailureTracker",
    "QuestProgress",
    "QuestContributionDay",
    "QuestContributionEntry",
    "UserQuestPreference",
    "UserQuestBias",
    # Story / personality / rag
    "StoryArc",
    "ArcTrigger",
    "PersonalityState",
    "PersonalityMessage",
    "PersonalityMemory",
    "RagDocument",
    # Harmony / insights / strategy / anomalies
    "HarmonyDimension",
    "HarmonySnapshot",
    "Pattern",
    "Insight",
    "InsightEvidence",
    "StrategyTracking",
    "AnomalyScore",
    # Leisure
    "LeisureBudget",
    "SubstanceLimit",
    "SubstanceUsageLog",
    # XP
    "XpAward",
    "LevelUp",
    # Analytics
    "UserAnalytics",
    # Circuit breaker
    "CircuitBreakerState",
    # Processing
    "EntryIdempotencyClaim",
    "OutboxEvent",
    "ProcessingJob",
    "ProcessingJobAttempt",
    "ProcessingJobClaim",
]
