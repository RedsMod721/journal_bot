"""
Weighted XP distribution strategy.

Distributes XP proportionally based on confidence scores.
"""

from typing import TYPE_CHECKING

from app.core.xp.base import XPDistributionStrategy

if TYPE_CHECKING:
    from app.models.journal_entry import JournalEntry


class WeightedDistributor(XPDistributionStrategy):
    """
    Distributes XP proportionally based on confidence scores.

    Categories without confidence scores default to 1.0.

    Example:
        categories = {
            "themes": [{"id": "t1", "confidence": 0.9}, {"id": "t2", "confidence": 0.6}],
            "skills": [{"id": "s1", "confidence": 0.7}]
        }
        base_xp = 100
        total_weight = 0.9 + 0.6 + 0.7 = 2.2

        Result: {
            "theme:t1": 40.91,  # 100 * (0.9 / 2.2)
            "theme:t2": 27.27,  # 100 * (0.6 / 2.2)
            "skill:s1": 31.82   # 100 * (0.7 / 2.2)
        }
    """

    DEFAULT_CONFIDENCE = 1.0

    def distribute(
        self,
        entry: "JournalEntry",
        categories: dict,
        base_xp: float,
    ) -> dict[str, float]:
        """
        Distribute XP proportionally based on confidence scores.

        Args:
            entry: The JournalEntry being processed (unused in weighted distribution)
            categories: Dict with "themes" and "skills" lists, each item may have "confidence"
            base_xp: Total XP to distribute proportionally

        Returns:
            Dict mapping "theme:{id}" and "skill:{id}" keys to weighted XP amounts
        """
        themes = categories.get("themes", [])
        skills = categories.get("skills", [])

        if not themes and not skills:
            return {}

        # Calculate total weight
        total_weight = 0.0
        for theme in themes:
            total_weight += theme.get("confidence", self.DEFAULT_CONFIDENCE)
        for skill in skills:
            total_weight += skill.get("confidence", self.DEFAULT_CONFIDENCE)

        if total_weight == 0:
            return {}

        result: dict[str, float] = {}

        for theme in themes:
            confidence = theme.get("confidence", self.DEFAULT_CONFIDENCE)
            result[f"theme:{theme['id']}"] = base_xp * (confidence / total_weight)

        for skill in skills:
            confidence = skill.get("confidence", self.DEFAULT_CONFIDENCE)
            result[f"skill:{skill['id']}"] = base_xp * (confidence / total_weight)

        return result
