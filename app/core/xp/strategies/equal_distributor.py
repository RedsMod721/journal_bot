"""
Equal XP distribution strategy.

Distributes base XP equally among all detected themes and skills.
"""

from typing import TYPE_CHECKING

from app.core.xp.base import XPDistributionStrategy

if TYPE_CHECKING:
    from app.models.journal_entry import JournalEntry


class EqualDistributor(XPDistributionStrategy):
    """
    Distributes XP equally among all detected themes and skills.

    Example:
        categories = {
            "themes": [{"id": "t1"}, {"id": "t2"}],
            "skills": [{"id": "s1"}]
        }
        base_xp = 60

        Result: {"theme:t1": 20.0, "theme:t2": 20.0, "skill:s1": 20.0}
    """

    def distribute(
        self,
        entry: "JournalEntry",
        categories: dict,
        base_xp: float,
    ) -> dict[str, float]:
        """
        Distribute XP equally across all themes and skills.

        Args:
            entry: The JournalEntry being processed (unused in equal distribution)
            categories: Dict with "themes" and "skills" lists
            base_xp: Total XP to distribute equally

        Returns:
            Dict mapping "theme:{id}" and "skill:{id}" keys to equal XP amounts
        """
        if categories is None:
            categories = {}

        themes = categories.get("themes") or []
        skills = categories.get("skills") or []

        total_targets = len(themes) + len(skills)

        if total_targets == 0:
            return {}

        xp_per_target = base_xp / total_targets

        result: dict[str, float] = {}

        for theme in themes:
            result[f"theme:{theme['id']}"] = xp_per_target

        for skill in skills:
            result[f"skill:{skill['id']}"] = xp_per_target

        return result
