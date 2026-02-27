"""
Base classes for XP distribution strategies.

This module defines the Strategy Pattern interface for XP distribution.
Different strategies can implement various XP allocation algorithms
(e.g., equal distribution, time-weighted, sentiment-based).

Example usage:
    class EqualDistributionStrategy(XPDistributionStrategy):
        def distribute(self, entry, categories, base_xp):
            # Distribute XP equally among all detected themes/skills
            ...

    strategy = EqualDistributionStrategy()
    xp_awards = strategy.distribute(entry, categories, base_xp=10.0)
    # Returns: {"theme:uuid-1": 10.0, "skill:uuid-2": 10.0}
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.journal_entry import JournalEntry


@dataclass
class XPTarget:
    """
    Represents a target entity for XP distribution.

    Attributes:
        target_type: The type of target ("theme" or "skill")
        target_id: The UUID of the target entity
        xp_amount: The amount of XP to award
    """

    target_type: str  # "theme" or "skill"
    target_id: str
    xp_amount: float

    def __post_init__(self) -> None:
        """Validate target_type."""
        valid_types = {"theme", "skill"}
        if self.target_type not in valid_types:
            raise ValueError(f"target_type must be one of {valid_types}, got '{self.target_type}'")

    @property
    def key(self) -> str:
        """Return the dictionary key format for this target."""
        return f"{self.target_type}:{self.target_id}"


class XPDistributionStrategy(ABC):
    """
    Abstract base class for XP distribution strategies.

    The Strategy Pattern allows different XP distribution algorithms to be
    swapped interchangeably. Each strategy determines how base XP is allocated
    across detected themes and skills from a journal entry.

    Strategies might consider:
    - Equal distribution across all categories
    - Weighted distribution based on practice time
    - Sentiment-based multipliers
    - First-mention bonuses for new themes/skills

    The categories dict follows the structure from JournalEntry.ai_categories:
        {
            "themes": [{"id": "theme-uuid-1", "name": "Education"}, ...],
            "skills": [{"id": "skill-uuid-1", "name": "Python"}, ...]
        }
    """

    @abstractmethod
    def distribute(
        self,
        entry: "JournalEntry",
        categories: dict,
        base_xp: float,
    ) -> dict[str, float]:
        """
        Distribute XP across themes and skills from a journal entry.

        Args:
            entry: The JournalEntry being processed. Provides access to
                   content, timestamps, and other entry metadata that
                   strategies may use for XP calculations.
            categories: Dict containing detected themes and skills.
                       Structure: {
                           "themes": [{"id": str, "name": str}, ...],
                           "skills": [{"id": str, "name": str}, ...]
                       }
            base_xp: The base XP amount to distribute. Strategies may
                    multiply, divide, or otherwise transform this value.

        Returns:
            Dict mapping target keys to XP amounts.
            Keys are formatted as "{type}:{id}" (e.g., "theme:uuid-1").
            Example: {"theme:abc-123": 10.0, "skill:def-456": 15.0}

        Raises:
            NotImplementedError: If the subclass does not implement this method.
        """
        raise NotImplementedError("Subclasses must implement distribute()")
