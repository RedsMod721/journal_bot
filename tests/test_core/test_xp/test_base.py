"""
Tests for XP distribution strategy base interfaces.
"""
import pytest

from app.core.xp.base import XPTarget, XPDistributionStrategy


class DummyStrategy(XPDistributionStrategy):
    def distribute(self, entry, categories, base_xp):
        return {}


class ParentStrategy(XPDistributionStrategy):
    def distribute(self, entry, categories, base_xp):
        return super().distribute(entry, categories, base_xp)


class TestXPDistributionStrategyBase:
    def test_xp_distribution_strategy_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            XPDistributionStrategy()

    def test_xp_distribution_strategy_subclass_implements(self) -> None:
        strategy = DummyStrategy()
        result = strategy.distribute(entry=None, categories={}, base_xp=1.0)
        assert result == {}

    def test_xp_distribution_strategy_base_raises(self) -> None:
        strategy = ParentStrategy()
        with pytest.raises(NotImplementedError):
            strategy.distribute(entry=None, categories={}, base_xp=1.0)


class TestXPTarget:
    def test_xp_target_dataclass_creation(self) -> None:
        target = XPTarget(target_type="theme", target_id="theme-123", xp_amount=10.5)

        assert target.target_type == "theme"
        assert target.target_id == "theme-123"
        assert target.xp_amount == 10.5

    def test_xp_target_key_format(self) -> None:
        target = XPTarget(target_type="skill", target_id="skill-abc", xp_amount=5.0)

        assert target.key == "skill:skill-abc"

    def test_xp_target_invalid_type_raises(self) -> None:
        with pytest.raises(ValueError, match="target_type must be one of"):
            XPTarget(target_type="invalid", target_id="x", xp_amount=1.0)

    def test_xp_target_allows_zero_and_negative_xp(self) -> None:
        zero = XPTarget(target_type="theme", target_id="t1", xp_amount=0.0)
        negative = XPTarget(target_type="theme", target_id="t2", xp_amount=-5.0)

        assert zero.xp_amount == 0.0
        assert negative.xp_amount == -5.0
