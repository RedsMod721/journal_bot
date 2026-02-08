"""
Tests for EqualDistributor XP strategy.
"""
import pytest

from app.core.xp.strategies.equal_distributor import EqualDistributor


class TestEqualDistributor:
    def test_equal_distribution_with_multiple_themes_and_skills(self) -> None:
        strategy = EqualDistributor()
        categories = {
            "themes": [{"id": "t1"}, {"id": "t2"}],
            "skills": [{"id": "s1"}],
        }

        result = strategy.distribute(entry=None, categories=categories, base_xp=60.0)

        assert result == {"theme:t1": 20.0, "theme:t2": 20.0, "skill:s1": 20.0}

    def test_equal_distribution_themes_only(self) -> None:
        strategy = EqualDistributor()
        categories = {"themes": [{"id": "t1"}, {"id": "t2"}], "skills": []}

        result = strategy.distribute(entry=None, categories=categories, base_xp=40.0)

        assert result == {"theme:t1": 20.0, "theme:t2": 20.0}

    def test_equal_distribution_skills_only(self) -> None:
        strategy = EqualDistributor()
        categories = {"themes": [], "skills": [{"id": "s1"}, {"id": "s2"}]}

        result = strategy.distribute(entry=None, categories=categories, base_xp=50.0)

        assert result == {"skill:s1": 25.0, "skill:s2": 25.0}

    def test_equal_distribution_no_targets_returns_empty(self) -> None:
        strategy = EqualDistributor()

        result = strategy.distribute(entry=None, categories={}, base_xp=100.0)

        assert result == {}

    def test_equal_distribution_none_categories_returns_empty(self) -> None:
        strategy = EqualDistributor()

        result = strategy.distribute(entry=None, categories=None, base_xp=100.0)

        assert result == {}

    def test_equal_distribution_none_lists_returns_empty(self) -> None:
        strategy = EqualDistributor()
        categories = {"themes": None, "skills": None}

        result = strategy.distribute(entry=None, categories=categories, base_xp=50.0)

        assert result == {}

    def test_equal_distribution_single_target_gets_all_xp(self) -> None:
        strategy = EqualDistributor()
        categories = {"themes": [{"id": "t1"}], "skills": []}

        result = strategy.distribute(entry=None, categories=categories, base_xp=33.0)

        assert result == {"theme:t1": 33.0}

    def test_equal_distribution_handles_odd_numbers(self) -> None:
        strategy = EqualDistributor()
        categories = {"themes": [{"id": "t1"}, {"id": "t2"}], "skills": [{"id": "s1"}]}

        result = strategy.distribute(entry=None, categories=categories, base_xp=100.0)

        assert result["theme:t1"] == pytest.approx(33.3333333333)
        assert result["theme:t2"] == pytest.approx(33.3333333333)
        assert result["skill:s1"] == pytest.approx(33.3333333333)

    def test_equal_distribution_preserves_total_xp(self) -> None:
        strategy = EqualDistributor()
        categories = {"themes": [{"id": "t1"}], "skills": [{"id": "s1"}, {"id": "s2"}]}

        result = strategy.distribute(entry=None, categories=categories, base_xp=75.0)

        assert sum(result.values()) == pytest.approx(75.0)

    def test_equal_distribution_zero_base_xp(self) -> None:
        strategy = EqualDistributor()
        categories = {"themes": [{"id": "t1"}], "skills": [{"id": "s1"}]}

        result = strategy.distribute(entry=None, categories=categories, base_xp=0.0)

        assert result == {"theme:t1": 0.0, "skill:s1": 0.0}

    def test_equal_distribution_negative_base_xp(self) -> None:
        strategy = EqualDistributor()
        categories = {"themes": [{"id": "t1"}], "skills": [{"id": "s1"}]}

        result = strategy.distribute(entry=None, categories=categories, base_xp=-10.0)

        assert result == {"theme:t1": -5.0, "skill:s1": -5.0}

    def test_equal_distribution_ignores_extra_fields(self) -> None:
        strategy = EqualDistributor()
        categories = {
            "themes": [{"id": "t1", "name": "Theme"}],
            "skills": [{"id": "s1", "name": "Skill"}],
        }

        result = strategy.distribute(entry=None, categories=categories, base_xp=20.0)

        assert result == {"theme:t1": 10.0, "skill:s1": 10.0}
