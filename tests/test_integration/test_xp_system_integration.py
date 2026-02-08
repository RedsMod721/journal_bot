"""
Integration tests for the complete XP system.

Tests the full XP flow from journal entry creation through XP distribution,
multiplier application, level-ups, and event emission.
"""

import pytest
from unittest.mock import MagicMock

from app.core.config_loader import ConfigLoader
from app.core.events import EventBus
from app.core.xp import (
    EqualDistributor,
    ProportionalDistributor,
    WeightedDistributor,
    XPCalculator,
)
from app.models.journal_entry import JournalEntry
from app.models.skill import Skill
from app.models.theme import Theme
from app.models.title import TitleTemplate, UserTitle
from app.models.user import User


class TestCompleteXPFlow:
    """Test full XP flow: journal entry → XP award → level up → event cascade."""

    def test_complete_xp_flow_from_journal_to_level_up(self, db_session, fake):
        """Test full XP flow: journal entry → XP award → level up → event cascade."""
        # 1. Create user with theme and skill
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(
            user_id=user.id,
            name="Education",
            description="Learning",
            xp=90.0,  # Close to level up (100 XP needed)
            xp_to_next_level=100.0,
        )
        skill = Skill(
            user_id=user.id,
            name="Python",
            description="Programming",
            xp=45.0,  # Close to level up (50 XP needed)
            xp_to_next_level=50.0,
        )
        db_session.add_all([theme, skill])
        db_session.commit()

        # 2. Create a title with XP multiplier and equip it
        title_template = TitleTemplate(
            name="Scholar",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Education",
                "value": 1.20,  # +20% Education XP
            },
            rank="B",
        )
        db_session.add(title_template)
        db_session.commit()

        user_title = UserTitle(
            user_id=user.id,
            title_template_id=title_template.id,
            is_equipped=True,
        )
        db_session.add(user_title)
        db_session.commit()

        # 3. Create journal entry
        entry = JournalEntry(
            user_id=user.id,
            content="Today I studied Python programming and learned about Education topics.",
            entry_type="text",
        )
        db_session.add(entry)
        db_session.commit()

        # 4. Mock categories (simulating AI response)
        categories = {
            "themes": [{"id": theme.id, "name": "Education"}],
            "skills": [{"id": skill.id, "name": "Python"}],
        }

        # 5. Set up event bus with mock listener
        event_bus = EventBus()
        captured_events = []

        def capture_event(payload):
            captured_events.append(payload)

        event_bus.subscribe("xp.awarded", capture_event)

        # 6. Set up config
        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 60.0  # 60 base XP

        # 7. Create calculator and process entry
        calculator = XPCalculator(
            strategy=EqualDistributor(),
            event_bus=event_bus,
            config=config,
        )

        # Record initial levels
        initial_theme_level = theme.level
        initial_skill_level = skill.level

        summary = calculator.process_journal_entry(db_session, entry, categories)

        # 8. Verify XP distributed correctly
        assert summary["total_xp"] > 0
        assert len(summary["awards"]) == 2

        # 9. Verify multipliers applied
        # Theme should get 30 * 1.20 = 36 XP (base 60 / 2 targets * 1.20 multiplier)
        theme_award = next(a for a in summary["awards"] if a["type"] == "theme")
        assert theme_award["xp"] == pytest.approx(36.0)  # 30 * 1.20

        # Skill should get 30 XP (no multiplier)
        skill_award = next(a for a in summary["awards"] if a["type"] == "skill")
        assert skill_award["xp"] == pytest.approx(30.0)

        # 10. Verify level-ups triggered
        db_session.refresh(theme)
        db_session.refresh(skill)

        # Theme: 90 + 36 = 126 XP -> level up (100 needed)
        assert theme.level == initial_theme_level + 1

        # Skill: 45 + 30 = 75 XP -> level up (50 needed)
        assert skill.level == initial_skill_level + 1

        # 11. Verify events emitted
        assert len(captured_events) == 2
        assert any(e["target_type"] == "theme" for e in captured_events)
        assert any(e["target_type"] == "skill" for e in captured_events)

        # 12. Verify xp_breakdown updated
        assert theme.theme_metadata.get("xp_breakdown", {}).get("journal") == pytest.approx(36.0)
        assert skill.skill_metadata.get("xp_breakdown", {}).get("journal") == pytest.approx(30.0)


class TestXPStrategies:
    """Test that all three strategies produce valid results."""

    def test_xp_system_with_all_three_strategies(self, db_session, fake):
        """Test that all three strategies produce valid results."""
        # Create user with theme and skill
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education")
        skill = Skill(user_id=user.id, name="Python")
        db_session.add_all([theme, skill])
        db_session.commit()

        # Create journal entry with content mentioning both
        entry = JournalEntry(
            user_id=user.id,
            content="Python Python Education",  # 2 Python, 1 Education
            entry_type="text",
        )
        db_session.add(entry)
        db_session.commit()

        categories = {
            "themes": [{"id": theme.id, "name": "Education", "confidence": 0.6}],
            "skills": [{"id": skill.id, "name": "Python", "confidence": 0.9}],
        }

        # Set up shared infrastructure
        event_bus = EventBus()
        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 90.0  # 90 base XP

        base_xp = 90.0
        results = {}

        # Test EqualDistributor
        theme.xp = 0
        skill.xp = 0
        theme.theme_metadata = {}
        skill.skill_metadata = {}
        db_session.commit()

        calc_equal = XPCalculator(EqualDistributor(), event_bus, config)
        results["equal"] = calc_equal.process_journal_entry(db_session, entry, categories)

        # Test WeightedDistributor
        theme.xp = 0
        skill.xp = 0
        theme.theme_metadata = {}
        skill.skill_metadata = {}
        db_session.commit()

        calc_weighted = XPCalculator(WeightedDistributor(), event_bus, config)
        results["weighted"] = calc_weighted.process_journal_entry(db_session, entry, categories)

        # Test ProportionalDistributor
        theme.xp = 0
        skill.xp = 0
        theme.theme_metadata = {}
        skill.skill_metadata = {}
        db_session.commit()

        calc_proportional = XPCalculator(ProportionalDistributor(), event_bus, config)
        results["proportional"] = calc_proportional.process_journal_entry(db_session, entry, categories)

        # Verify all strategies preserve total XP
        for strategy_name, summary in results.items():
            assert summary["total_xp"] == pytest.approx(base_xp), f"{strategy_name} should preserve total XP"
            assert len(summary["awards"]) == 2, f"{strategy_name} should have 2 awards"

        # Verify equal distribution gives equal amounts
        equal_awards = results["equal"]["awards"]
        assert equal_awards[0]["xp"] == pytest.approx(equal_awards[1]["xp"])

        # Verify weighted distribution follows confidence ratios
        # confidence: Education=0.6, Python=0.9, total=1.5
        weighted_awards = results["weighted"]["awards"]
        theme_award = next(a for a in weighted_awards if a["type"] == "theme")
        skill_award = next(a for a in weighted_awards if a["type"] == "skill")
        assert theme_award["xp"] == pytest.approx(90 * (0.6 / 1.5))  # 36
        assert skill_award["xp"] == pytest.approx(90 * (0.9 / 1.5))  # 54

        # Verify proportional distribution follows word count ratios
        # Word count: Python=2, Education=1, total=3
        proportional_awards = results["proportional"]["awards"]
        theme_award = next(a for a in proportional_awards if a["type"] == "theme")
        skill_award = next(a for a in proportional_awards if a["type"] == "skill")
        assert theme_award["xp"] == pytest.approx(90 * (1 / 3))  # 30
        assert skill_award["xp"] == pytest.approx(90 * (2 / 3))  # 60


class TestXPAccumulation:
    """Test XP accumulation across multiple journal entries."""

    def test_xp_system_multiple_entries_accumulate(self, db_session, fake):
        """Test XP accumulation across multiple journal entries."""
        # Create user with theme and skill
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education")
        skill = Skill(user_id=user.id, name="Python")
        db_session.add_all([theme, skill])
        db_session.commit()

        categories = {
            "themes": [{"id": theme.id, "name": "Education"}],
            "skills": [{"id": skill.id, "name": "Python"}],
        }

        # Set up infrastructure
        event_bus = EventBus()
        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 20.0  # 20 base XP per entry

        calculator = XPCalculator(EqualDistributor(), event_bus, config)

        # Process 5 entries
        total_theme_xp = 0.0
        total_skill_xp = 0.0

        for i in range(5):
            entry = JournalEntry(
                user_id=user.id,
                content=f"Journal entry {i + 1} about Python and Education.",
                entry_type="text",
            )
            db_session.add(entry)
            db_session.commit()

            summary = calculator.process_journal_entry(db_session, entry, categories)

            # Each entry distributes 20 XP equally: 10 to theme, 10 to skill
            theme_award = next(a for a in summary["awards"] if a["type"] == "theme")
            skill_award = next(a for a in summary["awards"] if a["type"] == "skill")

            total_theme_xp += theme_award["xp"]
            total_skill_xp += skill_award["xp"]

        # Verify accumulated XP
        db_session.refresh(theme)
        db_session.refresh(skill)

        # 5 entries * 10 XP each = 50 XP per target
        assert total_theme_xp == pytest.approx(50.0)
        assert total_skill_xp == pytest.approx(50.0)

        # Theme and skill should have leveled up (50 XP awarded, 50 XP threshold)
        assert skill.level >= 1  # 50 XP >= 50 threshold

        # Verify xp_breakdown accumulated correctly
        assert theme.theme_metadata["xp_breakdown"]["journal"] == pytest.approx(50.0)
        assert skill.skill_metadata["xp_breakdown"]["journal"] == pytest.approx(50.0)


class TestComplexMultiplierStacking:
    """Test complex multiplier scenarios with multiple equipped titles."""

    def test_xp_multiplier_stacking_complex_scenario(self, db_session, fake):
        """Test complex multiplier scenario with 5 equipped titles."""
        # Create user with theme
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education")
        db_session.add(theme)
        db_session.commit()

        # Create 5 titles with various multipliers
        titles_data = [
            # Title 1: Specific Education multiplier
            {
                "name": "Scholar",
                "effect": {
                    "type": "xp_multiplier",
                    "scope": "theme",
                    "target": "Education",
                    "value": 1.10,  # +10%
                },
                "rank": "C",
            },
            # Title 2: All themes multiplier
            {
                "name": "Lifelong Learner",
                "effect": {
                    "type": "xp_multiplier",
                    "scope": "theme",
                    "target": "all",
                    "value": 1.15,  # +15%
                },
                "rank": "B",
            },
            # Title 3: Global all XP multiplier
            {
                "name": "Overachiever",
                "effect": {
                    "type": "xp_multiplier",
                    "scope": "all",
                    "target": "all",
                    "value": 1.20,  # +20%
                },
                "rank": "A",
            },
            # Title 4: Another specific Education multiplier
            {
                "name": "Academic",
                "effect": {
                    "type": "xp_multiplier",
                    "scope": "theme",
                    "target": "Education",
                    "value": 1.05,  # +5%
                },
                "rank": "D",
            },
            # Title 5: Non-matching title (Health)
            {
                "name": "Athlete",
                "effect": {
                    "type": "xp_multiplier",
                    "scope": "theme",
                    "target": "Health",
                    "value": 1.50,  # +50% (should not apply)
                },
                "rank": "B",
            },
        ]

        for title_data in titles_data:
            template = TitleTemplate(**title_data)
            db_session.add(template)
            db_session.commit()

            user_title = UserTitle(
                user_id=user.id,
                title_template_id=template.id,
                is_equipped=True,
            )
            db_session.add(user_title)

        db_session.commit()

        # Create journal entry
        entry = JournalEntry(
            user_id=user.id,
            content="Studying Education today.",
            entry_type="text",
        )
        db_session.add(entry)
        db_session.commit()

        categories = {
            "themes": [{"id": theme.id, "name": "Education"}],
            "skills": [],
        }

        # Set up infrastructure
        event_bus = EventBus()
        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 100.0  # 100 base XP

        calculator = XPCalculator(EqualDistributor(), event_bus, config)
        summary = calculator.process_journal_entry(db_session, entry, categories)

        # Calculate expected multiplier:
        # Scholar (1.10) × Lifelong Learner (1.15) × Overachiever (1.20) × Academic (1.05)
        # = 1.10 × 1.15 × 1.20 × 1.05 = 1.5939
        # Athlete (Health) should NOT apply
        expected_multiplier = 1.10 * 1.15 * 1.20 * 1.05
        expected_xp = 100.0 * expected_multiplier

        assert len(summary["awards"]) == 1
        assert summary["awards"][0]["xp"] == pytest.approx(expected_xp)
        assert summary["total_xp"] == pytest.approx(expected_xp)

        # Verify the breakdown
        db_session.refresh(theme)
        assert theme.theme_metadata["xp_breakdown"]["journal"] == pytest.approx(expected_xp)

    def test_multipliers_only_apply_to_matching_targets(self, db_session, fake):
        """Test that multipliers only apply to their intended targets."""
        # Create user with two themes
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        education_theme = Theme(user_id=user.id, name="Education")
        health_theme = Theme(user_id=user.id, name="Health")
        db_session.add_all([education_theme, health_theme])
        db_session.commit()

        # Create title that only affects Education
        template = TitleTemplate(
            name="Scholar",
            effect={
                "type": "xp_multiplier",
                "scope": "theme",
                "target": "Education",
                "value": 2.0,  # Double XP
            },
            rank="A",
        )
        db_session.add(template)
        db_session.commit()

        user_title = UserTitle(
            user_id=user.id,
            title_template_id=template.id,
            is_equipped=True,
        )
        db_session.add(user_title)
        db_session.commit()

        # Create journal entry mentioning both themes
        entry = JournalEntry(
            user_id=user.id,
            content="Education and Health topics.",
            entry_type="text",
        )
        db_session.add(entry)
        db_session.commit()

        categories = {
            "themes": [
                {"id": education_theme.id, "name": "Education"},
                {"id": health_theme.id, "name": "Health"},
            ],
            "skills": [],
        }

        # Set up infrastructure
        event_bus = EventBus()
        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 100.0  # 100 base XP

        calculator = XPCalculator(EqualDistributor(), event_bus, config)
        summary = calculator.process_journal_entry(db_session, entry, categories)

        # Base: 50 XP each (100 / 2)
        # Education gets 2.0x = 100 XP
        # Health gets 1.0x = 50 XP
        # Total = 150 XP

        education_award = next(a for a in summary["awards"] if a["name"] == "Education")
        health_award = next(a for a in summary["awards"] if a["name"] == "Health")

        assert education_award["xp"] == pytest.approx(100.0)  # 50 * 2.0
        assert health_award["xp"] == pytest.approx(50.0)  # 50 * 1.0
        assert summary["total_xp"] == pytest.approx(150.0)


class TestEventEmission:
    """Test event emission during XP processing."""

    def test_events_contain_correct_payload(self, db_session, fake):
        """Test that emitted events contain all required fields."""
        # Create user with theme and skill
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education")
        skill = Skill(user_id=user.id, name="Python")
        db_session.add_all([theme, skill])
        db_session.commit()

        entry = JournalEntry(
            user_id=user.id,
            content="Education and Python.",
            entry_type="text",
        )
        db_session.add(entry)
        db_session.commit()

        categories = {
            "themes": [{"id": theme.id, "name": "Education"}],
            "skills": [{"id": skill.id, "name": "Python"}],
        }

        # Capture events
        event_bus = EventBus()
        captured_events = []
        event_bus.subscribe("xp.awarded", lambda p: captured_events.append(p))

        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 40.0

        calculator = XPCalculator(EqualDistributor(), event_bus, config)
        calculator.process_journal_entry(db_session, entry, categories)

        # Verify events
        assert len(captured_events) == 2

        for event in captured_events:
            # All required fields present
            assert "user_id" in event
            assert "amount" in event
            assert "source" in event
            assert "target_type" in event
            assert "target_id" in event

            # Correct values
            assert event["user_id"] == user.id
            assert event["source"] == "journal"
            assert event["amount"] == pytest.approx(20.0)
            assert event["target_type"] in ("theme", "skill")

    def test_no_events_when_no_targets(self, db_session, fake):
        """Test that no events are emitted when there are no targets."""
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        entry = JournalEntry(
            user_id=user.id,
            content="Random content.",
            entry_type="text",
        )
        db_session.add(entry)
        db_session.commit()

        # Empty categories
        categories = {"themes": [], "skills": []}

        # Capture events
        event_bus = EventBus()
        captured_events = []
        event_bus.subscribe("xp.awarded", lambda p: captured_events.append(p))

        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 100.0

        calculator = XPCalculator(EqualDistributor(), event_bus, config)
        summary = calculator.process_journal_entry(db_session, entry, categories)

        assert summary["total_xp"] == 0
        assert len(summary["awards"]) == 0
        assert len(captured_events) == 0


class TestXPEdgeCases:
    """Additional edge case coverage for XP calculator integration."""

    def test_weighted_distribution_missing_confidence_defaults_to_one(self, db_session, fake):
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education")
        skill = Skill(user_id=user.id, name="Python")
        db_session.add_all([theme, skill])
        db_session.commit()

        entry = JournalEntry(user_id=user.id, content="Education Python", entry_type="text")
        db_session.add(entry)
        db_session.commit()

        categories = {
            "themes": [{"id": theme.id, "name": theme.name}],
            "skills": [{"id": skill.id, "name": skill.name}],
        }

        event_bus = EventBus()
        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 90.0

        calculator = XPCalculator(WeightedDistributor(), event_bus, config)
        summary = calculator.process_journal_entry(db_session, entry, categories)

        # default confidence = 1.0 for both -> equal split
        theme_award = next(a for a in summary["awards"] if a["type"] == "theme")
        skill_award = next(a for a in summary["awards"] if a["type"] == "skill")
        assert theme_award["xp"] == pytest.approx(45.0)
        assert skill_award["xp"] == pytest.approx(45.0)

    def test_proportional_distribution_no_mentions_returns_empty(self, db_session, fake):
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education")
        skill = Skill(user_id=user.id, name="Python")
        db_session.add_all([theme, skill])
        db_session.commit()

        entry = JournalEntry(user_id=user.id, content="No keywords here", entry_type="text")
        db_session.add(entry)
        db_session.commit()

        categories = {
            "themes": [{"id": theme.id, "name": theme.name}],
            "skills": [{"id": skill.id, "name": skill.name}],
        }

        event_bus = EventBus()
        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 60.0

        calculator = XPCalculator(ProportionalDistributor(), event_bus, config)
        summary = calculator.process_journal_entry(db_session, entry, categories)

        assert summary["total_xp"] == 0
        assert summary["awards"] == []

    def test_zero_base_xp_still_emits_awards(self, db_session, fake):
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education")
        skill = Skill(user_id=user.id, name="Python")
        db_session.add_all([theme, skill])
        db_session.commit()

        entry = JournalEntry(user_id=user.id, content="Education Python", entry_type="text")
        db_session.add(entry)
        db_session.commit()

        categories = {
            "themes": [{"id": theme.id, "name": theme.name}],
            "skills": [{"id": skill.id, "name": skill.name}],
        }

        event_bus = EventBus()
        captured = []
        event_bus.subscribe("xp.awarded", lambda p: captured.append(p))

        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 0.0

        calculator = XPCalculator(EqualDistributor(), event_bus, config)
        summary = calculator.process_journal_entry(db_session, entry, categories)

        assert summary["total_xp"] == 0.0
        assert len(summary["awards"]) == 2
        assert len(captured) == 2
        assert all(a["xp"] == 0.0 for a in summary["awards"])

    def test_xp_breakdown_preserves_existing_sources(self, db_session, fake):
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education", theme_metadata={"xp_breakdown": {"quest": 5.0}})
        db_session.add(theme)
        db_session.commit()

        entry = JournalEntry(user_id=user.id, content="Education", entry_type="text")
        db_session.add(entry)
        db_session.commit()

        categories = {"themes": [{"id": theme.id, "name": theme.name}], "skills": []}

        event_bus = EventBus()
        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 20.0

        calculator = XPCalculator(EqualDistributor(), event_bus, config)
        calculator.process_journal_entry(db_session, entry, categories)

        db_session.refresh(theme)
        breakdown = theme.theme_metadata["xp_breakdown"]
        assert breakdown["quest"] == pytest.approx(5.0)
        assert breakdown["journal"] == pytest.approx(20.0)

    def test_multiplier_applies_to_all_scopes(self, db_session, fake):
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education")
        skill = Skill(user_id=user.id, name="Python")
        db_session.add_all([theme, skill])
        db_session.commit()

        template = TitleTemplate(
            name="GlobalBoost",
            effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.20},
            rank="A",
        )
        db_session.add(template)
        db_session.commit()

        db_session.add(UserTitle(user_id=user.id, title_template_id=template.id, is_equipped=True))
        db_session.commit()

        entry = JournalEntry(user_id=user.id, content="Education Python", entry_type="text")
        db_session.add(entry)
        db_session.commit()

        categories = {
            "themes": [{"id": theme.id, "name": theme.name}],
            "skills": [{"id": skill.id, "name": skill.name}],
        }

        event_bus = EventBus()
        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 40.0

        calculator = XPCalculator(EqualDistributor(), event_bus, config)
        summary = calculator.process_journal_entry(db_session, entry, categories)

        theme_award = next(a for a in summary["awards"] if a["type"] == "theme")
        skill_award = next(a for a in summary["awards"] if a["type"] == "skill")
        assert theme_award["xp"] == pytest.approx(24.0)
        assert skill_award["xp"] == pytest.approx(24.0)
        assert summary["total_xp"] == pytest.approx(48.0)

    def test_event_count_matches_awards(self, db_session, fake):
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education")
        skill = Skill(user_id=user.id, name="Python")
        db_session.add_all([theme, skill])
        db_session.commit()

        entry = JournalEntry(user_id=user.id, content="Education Python", entry_type="text")
        db_session.add(entry)
        db_session.commit()

        categories = {
            "themes": [{"id": theme.id, "name": theme.name}],
            "skills": [{"id": skill.id, "name": skill.name}],
        }

        event_bus = EventBus()
        captured = []
        event_bus.subscribe("xp.awarded", lambda p: captured.append(p))

        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 20.0

        calculator = XPCalculator(EqualDistributor(), event_bus, config)
        summary = calculator.process_journal_entry(db_session, entry, categories)

        assert len(captured) == len(summary["awards"])

    def test_unknown_target_type_from_strategy_is_ignored(self, db_session, fake):
        class BadStrategy:
            def distribute(self, entry, categories, base_xp):
                return {"unknown:123": 10.0}

        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        entry = JournalEntry(user_id=user.id, content="", entry_type="text")
        db_session.add(entry)
        db_session.commit()

        event_bus = EventBus()
        config = MagicMock(spec=ConfigLoader)
        config.get.return_value = 10.0

        calculator = XPCalculator(BadStrategy(), event_bus, config)
        summary = calculator.process_journal_entry(db_session, entry, {})

        assert summary["total_xp"] == 0.0
        assert summary["awards"] == []
