"""
Tests for WeightedDistributor XP strategy.
"""
import pytest

from app.core.xp.strategies.weighted_distributor import WeightedDistributor


class TestWeightedDistributor:
    def test_weighted_distribution_by_confidence(self) -> None:
        strategy = WeightedDistributor()
        categories = {
            "themes": [{"id": "t1", "confidence": 0.9}, {"id": "t2", "confidence": 0.6}],
            "skills": [{"id": "s1", "confidence": 0.7}],
        }

        result = strategy.distribute(entry=None, categories=categories, base_xp=100.0)

        assert result["theme:t1"] == pytest.approx(100.0 * (0.9 / 2.2))
        assert result["theme:t2"] == pytest.approx(100.0 * (0.6 / 2.2))
        assert result["skill:s1"] == pytest.approx(100.0 * (0.7 / 2.2))

    def test_weighted_distribution_missing_confidence_defaults_to_1(self) -> None:
        strategy = WeightedDistributor()
        categories = {
            "themes": [{"id": "t1"}],
            "skills": [{"id": "s1", "confidence": 3.0}],
        }

        result = strategy.distribute(entry=None, categories=categories, base_xp=80.0)

        total_weight = 1.0 + 3.0
        assert result["theme:t1"] == pytest.approx(80.0 * (1.0 / total_weight))
        assert result["skill:s1"] == pytest.approx(80.0 * (3.0 / total_weight))

    def test_weighted_distribution_all_equal_confidence_equals_equal_distribution(self) -> None:
        strategy = WeightedDistributor()
        categories = {
            "themes": [{"id": "t1", "confidence": 1.0}],
            "skills": [{"id": "s1", "confidence": 1.0}],
        }

        result = strategy.distribute(entry=None, categories=categories, base_xp=50.0)

        assert result == {"theme:t1": 25.0, "skill:s1": 25.0}

    def test_weighted_distribution_preserves_total_xp(self) -> None:
        strategy = WeightedDistributor()
        categories = {
            "themes": [{"id": "t1", "confidence": 0.2}, {"id": "t2", "confidence": 0.8}],
            "skills": [{"id": "s1", "confidence": 0.5}],
        }

        result = strategy.distribute(entry=None, categories=categories, base_xp=75.0)

        assert sum(result.values()) == pytest.approx(75.0)

    def test_weighted_distribution_no_targets_returns_empty(self) -> None:
        strategy = WeightedDistributor()

        result = strategy.distribute(entry=None, categories={}, base_xp=100.0)

        assert result == {}

    def test_weighted_distribution_single_target_with_confidence(self) -> None:
        strategy = WeightedDistributor()
        categories = {"themes": [{"id": "t1", "confidence": 0.25}], "skills": []}

        result = strategy.distribute(entry=None, categories=categories, base_xp=40.0)

        assert result == {"theme:t1": 40.0}

    def test_weighted_distribution_zero_total_weight_returns_empty(self) -> None:
        strategy = WeightedDistributor()
        categories = {
            "themes": [{"id": "t1", "confidence": 0.0}],
            "skills": [{"id": "s1", "confidence": 0.0}],
        }

        result = strategy.distribute(entry=None, categories=categories, base_xp=100.0)

        assert result == {}

    def test_weighted_distribution_negative_confidence(self) -> None:
        strategy = WeightedDistributor()
        categories = {
            "themes": [{"id": "t1", "confidence": -1.0}],
            "skills": [{"id": "s1", "confidence": 2.0}],
        }

        result = strategy.distribute(entry=None, categories=categories, base_xp=60.0)

        total_weight = -1.0 + 2.0
        assert result["theme:t1"] == pytest.approx(60.0 * (-1.0 / total_weight))
        assert result["skill:s1"] == pytest.approx(60.0 * (2.0 / total_weight))
