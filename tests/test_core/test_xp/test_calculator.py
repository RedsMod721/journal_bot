"""
Tests for XPCalculator orchestration.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.xp.calculator import XPCalculator
from app.core.xp.strategies.equal_distributor import EqualDistributor
from app.core.xp.strategies.proportional_distributor import ProportionalDistributor
from app.core.xp.strategies.weighted_distributor import WeightedDistributor
from app.models.title import TitleTemplate, UserTitle


class DummyConfig:
    def __init__(self, base_xp: float = 50.0):
        self.base_xp = base_xp

    def get(self, key: str, default=None):
        if key == "xp.base_journal_xp":
            return self.base_xp
        return default


def _make_event_bus():
    return SimpleNamespace(emit=MagicMock())


def _create_title(db_session, name: str, effect: dict):
    template = TitleTemplate(name=name, effect=effect, rank="C")
    db_session.add(template)
    db_session.commit()
    return template


def _equip_title(db_session, user_id: str, template_id: str, is_equipped: bool = True):
    user_title = UserTitle(
        user_id=user_id,
        title_template_id=template_id,
        is_equipped=is_equipped,
    )
    db_session.add(user_title)
    db_session.commit()
    return user_title


class TestXPCalculatorProcess:
    def test_process_journal_entry_distributes_xp(self, db_session, sample_user, sample_theme, sample_skill):
        strategy = EqualDistributor()
        event_bus = _make_event_bus()
        calculator = XPCalculator(strategy=strategy, event_bus=event_bus, config=DummyConfig(60.0))

        entry = SimpleNamespace(user_id=sample_user.id, content="")
        categories = {
            "themes": [{"id": sample_theme.id, "name": sample_theme.name}],
            "skills": [{"id": sample_skill.id, "name": sample_skill.name}],
        }

        summary = calculator.process_journal_entry(db_session, entry, categories)

        assert summary["total_xp"] == pytest.approx(60.0)
        assert len(summary["awards"]) == 2

    def test_process_journal_entry_applies_multipliers(self, db_session, sample_user, sample_theme):
        template = _create_title(
            db_session,
            "Scholar",
            {
                "type": "xp_multiplier",
                "scope": "theme",
                "target": sample_theme.name,
                "value": 1.10,
            },
        )
        _equip_title(db_session, sample_user.id, template.id, is_equipped=True)

        strategy = EqualDistributor()
        event_bus = _make_event_bus()
        calculator = XPCalculator(strategy=strategy, event_bus=event_bus, config=DummyConfig(50.0))

        entry = SimpleNamespace(user_id=sample_user.id, content="")
        categories = {"themes": [{"id": sample_theme.id, "name": sample_theme.name}], "skills": []}

        summary = calculator.process_journal_entry(db_session, entry, categories)

        assert summary["total_xp"] == pytest.approx(55.0)

    def test_process_journal_entry_updates_xp_breakdown(self, db_session, sample_user, sample_theme):
        strategy = EqualDistributor()
        event_bus = _make_event_bus()
        calculator = XPCalculator(strategy=strategy, event_bus=event_bus, config=DummyConfig(40.0))

        entry = SimpleNamespace(user_id=sample_user.id, content="")
        categories = {"themes": [{"id": sample_theme.id, "name": sample_theme.name}], "skills": []}

        calculator.process_journal_entry(db_session, entry, categories)

        db_session.refresh(sample_theme)
        assert sample_theme.theme_metadata["xp_breakdown"]["journal"] == pytest.approx(40.0)

    def test_process_journal_entry_emits_xp_awarded_events(self, db_session, sample_user, sample_theme):
        strategy = EqualDistributor()
        event_bus = _make_event_bus()
        calculator = XPCalculator(strategy=strategy, event_bus=event_bus, config=DummyConfig(30.0))

        entry = SimpleNamespace(user_id=sample_user.id, content="")
        categories = {"themes": [{"id": sample_theme.id, "name": sample_theme.name}], "skills": []}

        calculator.process_journal_entry(db_session, entry, categories)

        assert event_bus.emit.call_count == 1
        args, kwargs = event_bus.emit.call_args
        assert args[0] == "xp.awarded"
        assert kwargs == {}
        assert args[1]["user_id"] == sample_user.id

    def test_process_journal_entry_triggers_level_ups(self, db_session, sample_user, sample_theme):
        sample_theme.xp = 0
        sample_theme.xp_to_next_level = 5.0
        db_session.commit()

        strategy = EqualDistributor()
        event_bus = _make_event_bus()
        calculator = XPCalculator(strategy=strategy, event_bus=event_bus, config=DummyConfig(10.0))

        entry = SimpleNamespace(user_id=sample_user.id, content="")
        categories = {"themes": [{"id": sample_theme.id, "name": sample_theme.name}], "skills": []}

        calculator.process_journal_entry(db_session, entry, categories)

        db_session.refresh(sample_theme)
        assert sample_theme.level >= 1

    def test_process_journal_entry_handles_no_categories_gracefully(self, db_session, sample_user, sample_theme, sample_skill):
        strategy = EqualDistributor()
        event_bus = _make_event_bus()
        calculator = XPCalculator(strategy=strategy, event_bus=event_bus, config=DummyConfig(50.0))

        entry = SimpleNamespace(user_id=sample_user.id, content="")
        summary = calculator.process_journal_entry(db_session, entry, {})

        db_session.refresh(sample_theme)
        db_session.refresh(sample_skill)
        assert summary["total_xp"] == 0.0
        assert summary["awards"] == []
        assert event_bus.emit.call_count == 0

    def test_process_journal_entry_with_equal_strategy(self, db_session, sample_user, sample_theme, sample_skill):
        strategy = EqualDistributor()
        event_bus = _make_event_bus()
        calculator = XPCalculator(strategy=strategy, event_bus=event_bus, config=DummyConfig(60.0))

        entry = SimpleNamespace(user_id=sample_user.id, content="")
        categories = {
            "themes": [{"id": sample_theme.id, "name": sample_theme.name}],
            "skills": [{"id": sample_skill.id, "name": sample_skill.name}],
        }

        summary = calculator.process_journal_entry(db_session, entry, categories)

        assert summary["total_xp"] == pytest.approx(60.0)
        assert {award["type"] for award in summary["awards"]} == {"theme", "skill"}

    def test_process_journal_entry_with_weighted_strategy(self, db_session, sample_user, sample_theme, sample_skill):
        strategy = WeightedDistributor()
        event_bus = _make_event_bus()
        calculator = XPCalculator(strategy=strategy, event_bus=event_bus, config=DummyConfig(100.0))

        entry = SimpleNamespace(user_id=sample_user.id, content="")
        categories = {
            "themes": [{"id": sample_theme.id, "name": sample_theme.name, "confidence": 0.75}],
            "skills": [{"id": sample_skill.id, "name": sample_skill.name, "confidence": 0.25}],
        }

        summary = calculator.process_journal_entry(db_session, entry, categories)

        assert summary["total_xp"] == pytest.approx(100.0)

    def test_process_journal_entry_with_proportional_strategy(self, db_session, sample_user, sample_theme, sample_skill):
        strategy = ProportionalDistributor()
        event_bus = _make_event_bus()
        calculator = XPCalculator(strategy=strategy, event_bus=event_bus, config=DummyConfig(90.0))

        entry = SimpleNamespace(user_id=sample_user.id, content=f"{sample_skill.name} {sample_theme.name} {sample_skill.name}")
        categories = {
            "themes": [{"id": sample_theme.id, "name": sample_theme.name}],
            "skills": [{"id": sample_skill.id, "name": sample_skill.name}],
        }

        summary = calculator.process_journal_entry(db_session, entry, categories)

        assert summary["total_xp"] == pytest.approx(90.0)

    def test_xp_breakdown_accumulates_over_multiple_entries(self, db_session, sample_user, sample_theme):
        strategy = EqualDistributor()
        event_bus = _make_event_bus()
        calculator = XPCalculator(strategy=strategy, event_bus=event_bus, config=DummyConfig(20.0))

        entry = SimpleNamespace(user_id=sample_user.id, content="")
        categories = {"themes": [{"id": sample_theme.id, "name": sample_theme.name}], "skills": []}

        calculator.process_journal_entry(db_session, entry, categories)
        calculator.process_journal_entry(db_session, entry, categories)

        db_session.refresh(sample_theme)
        assert sample_theme.theme_metadata["xp_breakdown"]["journal"] == pytest.approx(40.0)


class TestXPCalculatorHelpers:
    def test_calculate_final_xp_with_multiple_titles(self, db_session, sample_user, sample_theme):
        template1 = _create_title(
            db_session,
            "Scholar",
            {"type": "xp_multiplier", "scope": "theme", "target": sample_theme.name, "value": 1.10},
        )
        template2 = _create_title(
            db_session,
            "AllThemes",
            {"type": "xp_multiplier", "scope": "theme", "target": "all", "value": 1.15},
        )
        template3 = _create_title(
            db_session,
            "AllXP",
            {"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.20},
        )
        for template in [template1, template2, template3]:
            _equip_title(db_session, sample_user.id, template.id, is_equipped=True)

        calculator = XPCalculator(strategy=EqualDistributor(), event_bus=_make_event_bus(), config=DummyConfig())

        final_xp = calculator._calculate_final_xp(
            db_session, base_xp=10.0, user_id=sample_user.id, target_type="theme", target_id=sample_theme.id
        )

        assert final_xp == pytest.approx(10.0 * 1.518)

    def test_award_to_theme_calls_crud_correctly(self, db_session, sample_theme):
        calculator = XPCalculator(strategy=EqualDistributor(), event_bus=_make_event_bus(), config=DummyConfig())

        before_xp = sample_theme.xp
        theme = calculator._award_to_theme(db_session, sample_theme.id, 5.0)

        assert theme is not None
        assert theme.xp > before_xp

    def test_award_to_skill_calls_crud_correctly(self, db_session, sample_skill):
        calculator = XPCalculator(strategy=EqualDistributor(), event_bus=_make_event_bus(), config=DummyConfig())

        before_xp = sample_skill.xp
        skill = calculator._award_to_skill(db_session, sample_skill.id, 5.0)

        assert skill is not None
        assert skill.xp > before_xp

    def test_calculate_final_xp_missing_target_returns_base(self, db_session, sample_user):
        calculator = XPCalculator(strategy=EqualDistributor(), event_bus=_make_event_bus(), config=DummyConfig())

        final_xp = calculator._calculate_final_xp(
            db_session, base_xp=12.0, user_id=sample_user.id, target_type="theme", target_id="missing"
        )

        assert final_xp == 12.0

    def test_award_to_theme_missing_returns_none(self, db_session):
        calculator = XPCalculator(strategy=EqualDistributor(), event_bus=_make_event_bus(), config=DummyConfig())

        assert calculator._award_to_theme(db_session, "missing", 5.0) is None

    def test_award_to_skill_missing_returns_none(self, db_session):
        calculator = XPCalculator(strategy=EqualDistributor(), event_bus=_make_event_bus(), config=DummyConfig())

        assert calculator._award_to_skill(db_session, "missing", 5.0) is None
