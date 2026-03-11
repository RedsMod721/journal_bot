from enum import Enum


class SkillState(str, Enum):
    """Skill unlock states in the hierarchy progression."""
    LOCKED = "locked"                    # Hidden, cannot gain XP
    DISCOVERED = "discovered"            # Visible (dimmed), cannot gain XP
    UNLOCKED_HIDDEN = "unlocked_hidden"  # Hidden, can gain XP when activated
    ACTIVATED = "activated"              # Visible, can gain XP


class SkillRank(str, Enum):
    """Rank thresholds mirroring the CHECK constraint on skills/themes."""
    F = "F"
    E = "E"
    D = "D"
    C = "C"
    B = "B"
    A = "A"
    S = "S"
    SS = "SS"
    SSS = "SSS"


SKILL_RANK_VALUES: tuple[str, ...] = tuple(rank.value for rank in SkillRank)


def get_rank_from_level(level: int) -> SkillRank:
    """Return the rank for a given skill level using canonical branch order."""
    # Gameplay ranks start at Lv1. Lv0 may still appear in transitional flows;
    # map it to F so all call sites get a valid rank string.
    if level < 10:
        return SkillRank.F
    if level < 20:
        return SkillRank.E
    if level < 30:
        return SkillRank.D
    if level < 40:
        return SkillRank.C
    if level < 50:
        return SkillRank.B
    if level < 60:
        return SkillRank.A
    if level < 75:
        return SkillRank.S
    if level < 100:
        return SkillRank.SS
    return SkillRank.SSS
