"""XP distribution system for Status Window API."""

from app.core.xp.base import XPDistributionStrategy, XPTarget
from app.core.xp.strategies import EqualDistributor

__all__ = ["XPDistributionStrategy", "XPTarget", "EqualDistributor"]
