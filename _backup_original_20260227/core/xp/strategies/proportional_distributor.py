"""
Proportional XP distribution strategy based on content mentions.

Week 2 stub: Uses simple word counting.
Week 3: Will be enhanced with spaCy NLP for better detection.
"""

import re
from typing import TYPE_CHECKING

from app.core.xp.base import XPDistributionStrategy

if TYPE_CHECKING:
    from app.models.journal_entry import JournalEntry


class ProportionalDistributor(XPDistributionStrategy):
    """
    Distributes XP proportionally based on content mentions.

    Counts occurrences of theme/skill names in entry content and
    distributes XP proportionally to mention frequency.

    Example:
        entry.content = "Studied Python for 2 hours. Python is great. Also read about Education."
        categories = {
            "themes": [{"id": "t1", "name": "Education"}],
            "skills": [{"id": "s1", "name": "Python"}]
        }
        Word counts: Python=2, Education=1, Total=3

        Result: {
            "skill:s1": 66.67,  # 100 * (2/3)
            "theme:t1": 33.33   # 100 * (1/3)
        }

    Note: This is a Week 2 stub using simple word counting.
          Week 3 will enhance with spaCy NLP for better detection.
    """

    def distribute(
        self,
        entry: "JournalEntry",
        categories: dict,
        base_xp: float,
    ) -> dict[str, float]:
        """
        Distribute XP proportionally based on content mentions.

        Args:
            entry: The JournalEntry with content to analyze
            categories: Dict with "themes" and "skills" lists, each with "id" and "name"
            base_xp: Total XP to distribute proportionally

        Returns:
            Dict mapping "theme:{id}" and "skill:{id}" keys to proportional XP amounts
        """
        themes = categories.get("themes", [])
        skills = categories.get("skills", [])

        if not themes and not skills:
            return {}

        content = entry.content.lower() if entry and entry.content else ""

        # Count mentions for each target
        mention_counts: list[tuple[str, str, int]] = []  # (type, id, count)

        for theme in themes:
            name = theme.get("name", "")
            if name:
                count = self._count_mentions(content, name)
                mention_counts.append(("theme", theme["id"], count))

        for skill in skills:
            name = skill.get("name", "")
            if name:
                count = self._count_mentions(content, name)
                mention_counts.append(("skill", skill["id"], count))

        # Calculate total mentions
        total_mentions = sum(count for _, _, count in mention_counts)

        if total_mentions == 0:
            return {}

        # Distribute XP proportionally
        result: dict[str, float] = {}
        for target_type, target_id, count in mention_counts:
            if count > 0:
                result[f"{target_type}:{target_id}"] = base_xp * (count / total_mentions)

        return result

    def _count_mentions(self, content: str, name: str) -> int:
        """
        Count case-insensitive word boundary matches of name in content.

        Args:
            content: Lowercase content to search
            name: Name to search for

        Returns:
            Number of occurrences
        """
        pattern = re.compile(rf"\b{re.escape(name.lower())}\b", re.IGNORECASE)
        return len(pattern.findall(content))
