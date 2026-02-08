"""
Tests for ProportionalDistributor XP strategy.
"""
from types import SimpleNamespace

import pytest

from app.core.xp.strategies.proportional_distributor import ProportionalDistributor


class TestProportionalDistributor:
    def test_proportional_distribution_by_word_count(self) -> None:
        strategy = ProportionalDistributor()
        entry = SimpleNamespace(
            content="Studied Python for 2 hours. Python is great. Also read about Education."
        )
        categories = {
            "themes": [{"id": "t1", "name": "Education"}],
            "skills": [{"id": "s1", "name": "Python"}],
        }

        result = strategy.distribute(entry=entry, categories=categories, base_xp=100.0)

        assert result["skill:s1"] == pytest.approx(100.0 * (2 / 3))
        assert result["theme:t1"] == pytest.approx(100.0 * (1 / 3))

    def test_proportional_distribution_case_insensitive(self) -> None:
        strategy = ProportionalDistributor()
        entry = SimpleNamespace(content="python PYTHON PyThOn education")
        categories = {
            "themes": [{"id": "t1", "name": "Education"}],
            "skills": [{"id": "s1", "name": "Python"}],
        }

        result = strategy.distribute(entry=entry, categories=categories, base_xp=40.0)

        assert result["skill:s1"] == pytest.approx(40.0 * (3 / 4))
        assert result["theme:t1"] == pytest.approx(40.0 * (1 / 4))

    def test_proportional_distribution_no_mentions_returns_empty(self) -> None:
        strategy = ProportionalDistributor()
        entry = SimpleNamespace(content="No relevant keywords here.")
        categories = {
            "themes": [{"id": "t1", "name": "Education"}],
            "skills": [{"id": "s1", "name": "Python"}],
        }

        result = strategy.distribute(entry=entry, categories=categories, base_xp=100.0)

        assert result == {}

    def test_proportional_distribution_single_mention(self) -> None:
        strategy = ProportionalDistributor()
        entry = SimpleNamespace(content="Worked on Python.")
        categories = {
            "themes": [{"id": "t1", "name": "Education"}],
            "skills": [{"id": "s1", "name": "Python"}],
        }

        result = strategy.distribute(entry=entry, categories=categories, base_xp=90.0)

        assert result == {"skill:s1": 90.0}

    def test_proportional_distribution_preserves_total_xp(self) -> None:
        strategy = ProportionalDistributor()
        entry = SimpleNamespace(content="Python and Education. Python and Education.")
        categories = {
            "themes": [{"id": "t1", "name": "Education"}],
            "skills": [{"id": "s1", "name": "Python"}],
        }

        result = strategy.distribute(entry=entry, categories=categories, base_xp=75.0)

        assert sum(result.values()) == pytest.approx(75.0)

    def test_proportional_distribution_handles_punctuation(self) -> None:
        strategy = ProportionalDistributor()
        entry = SimpleNamespace(content="Python, Python! Education?")
        categories = {
            "themes": [{"id": "t1", "name": "Education"}],
            "skills": [{"id": "s1", "name": "Python"}],
        }

        result = strategy.distribute(entry=entry, categories=categories, base_xp=30.0)

        assert result["skill:s1"] == pytest.approx(20.0)
        assert result["theme:t1"] == pytest.approx(10.0)

    def test_proportional_distribution_empty_content_returns_empty(self) -> None:
        strategy = ProportionalDistributor()
        entry = SimpleNamespace(content="")
        categories = {
            "themes": [{"id": "t1", "name": "Education"}],
            "skills": [{"id": "s1", "name": "Python"}],
        }

        result = strategy.distribute(entry=entry, categories=categories, base_xp=50.0)

        assert result == {}

    def test_proportional_distribution_ignores_missing_names(self) -> None:
        strategy = ProportionalDistributor()
        entry = SimpleNamespace(content="Python Education")
        categories = {
            "themes": [{"id": "t1"}],
            "skills": [{"id": "s1", "name": "Python"}],
        }

        result = strategy.distribute(entry=entry, categories=categories, base_xp=20.0)

        assert result == {"skill:s1": 20.0}

    def test_proportional_distribution_no_targets_returns_empty(self) -> None:
        strategy = ProportionalDistributor()
        entry = SimpleNamespace(content="Python")

        result = strategy.distribute(entry=entry, categories={}, base_xp=10.0)

        assert result == {}
