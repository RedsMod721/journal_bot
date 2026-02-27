"""
Pydantic models for game balance configuration.

These models provide type validation and documentation for the game_balance.yaml
configuration file. All values are validated on load and can be accessed with
full type safety.

Usage:
    from app.core.config_loader import get_config

    config = get_config()
    base_xp = config.get("xp.base_journal_xp")
"""
from pydantic import BaseModel, Field


class XPConfig(BaseModel):
    """Configuration for XP rewards and calculations."""

    base_journal_xp: int = Field(
        default=50,
        ge=1,
        description="Base XP awarded for each journal entry",
    )
    practice_time_multiplier: float = Field(
        default=0.5,
        ge=0.0,
        le=10.0,
        description="XP multiplier per minute of practice time",
    )


class LevelConfig(BaseModel):
    """Configuration for a single level progression type."""

    base_xp: int = Field(
        default=100,
        ge=1,
        description="Base XP required for first level",
    )
    scaling_factor: float = Field(
        default=1.15,
        ge=1.0,
        le=3.0,
        description="Exponential scaling factor for XP requirements",
    )


class LevelsConfig(BaseModel):
    """Configuration for level progression across different entity types."""

    theme: LevelConfig = Field(default_factory=LevelConfig)
    skill: LevelConfig = Field(default_factory=LevelConfig)


class TitleEffectMultipliers(BaseModel):
    """Multipliers for title effects by rank."""

    S_rank: float = Field(default=1.50, ge=1.0, le=5.0)
    A_rank: float = Field(default=1.30, ge=1.0, le=5.0)
    B_rank: float = Field(default=1.15, ge=1.0, le=5.0)
    C_rank: float = Field(default=1.10, ge=1.0, le=5.0)
    D_rank: float = Field(default=1.05, ge=1.0, le=5.0)
    E_rank: float = Field(default=1.02, ge=1.0, le=5.0)
    F_rank: float = Field(default=1.00, ge=1.0, le=5.0)


class TitlesConfig(BaseModel):
    """Configuration for title system."""

    effect_multipliers: TitleEffectMultipliers = Field(
        default_factory=TitleEffectMultipliers
    )


class QuestsConfig(BaseModel):
    """Configuration for quest rewards."""

    daily_xp_reward: int = Field(
        default=100,
        ge=0,
        description="XP reward for completing daily quests",
    )
    weekly_xp_reward: int = Field(
        default=500,
        ge=0,
        description="XP reward for completing weekly quests",
    )
    monthly_xp_reward: int = Field(
        default=2000,
        ge=0,
        description="XP reward for completing monthly quests",
    )


class KarmaConfig(BaseModel):
    """Configuration for karma system."""

    lecture_listen_karma: int = Field(
        default=10,
        description="Karma gained for listening to a lecture",
    )
    good_deed_karma: int = Field(
        default=5,
        description="Karma gained for performing a good deed",
    )
    negative_action_penalty: int = Field(
        default=-3,
        le=0,
        description="Karma penalty for negative actions (must be negative)",
    )


class ItemsConfig(BaseModel):
    """Configuration for item system."""

    knowledge_capsule_duration_days: int = Field(
        default=30,
        ge=1,
        description="Duration in days for knowledge capsule effects",
    )
    consumable_effects_duration_minutes: int = Field(
        default=60,
        ge=1,
        description="Duration in minutes for consumable item effects",
    )


class GameBalanceConfig(BaseModel):
    """Top-level game balance configuration containing all subsections."""

    xp: XPConfig = Field(default_factory=XPConfig)
    levels: LevelsConfig = Field(default_factory=LevelsConfig)
    titles: TitlesConfig = Field(default_factory=TitlesConfig)
    quests: QuestsConfig = Field(default_factory=QuestsConfig)
    karma: KarmaConfig = Field(default_factory=KarmaConfig)
    items: ItemsConfig = Field(default_factory=ItemsConfig)
