"""XP distribution system for Status Window API."""

from app.core.xp.base import XPDistributionStrategy, XPTarget
from app.core.xp.calculator import XPCalculator
from app.core.xp.multipliers import applies_to_target, calculate_title_multipliers
from app.core.xp.strategies import EqualDistributor, ProportionalDistributor, WeightedDistributor

__all__ = [
    "XPCalculator",
    "XPDistributionStrategy",
    "XPTarget",
    "EqualDistributor",
    "ProportionalDistributor",
    "WeightedDistributor",
    "applies_to_target",
    "calculate_title_multipliers",
]
