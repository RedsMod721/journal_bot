"""
Integration tests for the complete title system.

Tests the full title flow from condition met → title check → title awarded → event emitted.
Covers positive titles, negative titles, compound conditions, and user journey simulation.
"""

from datetime import datetime, timedelta

import pytest

from app.core.events import EventBus
from app.core.titles import TitleAwarder
from app.models.journal_entry import JournalEntry
from app.models.skill import Skill
from app.models.theme import Theme
from app.models.title import TitleTemplate, UserTitle
from app.models.user import User


class TestTitleUnlockCascade:
    """Test: Level up → Title check → Title awarded → Event emitted."""

    def test_title_unlock_cascade_from_level_up(self, db_session, fake):
        """
        Test full cascade: theme level up triggers title unlock and event emission.

        Flow:
        1. Create user with theme at level 9
        2. Create title template: "Education Novice" (theme_level >= 10)
        3. Add XP to theme to trigger level 10
        4. Run TitleAwarder.check_user_unlocks()
        5. Verify title awarded
        6. Verify "title.unlocked" event emitted
        7. Verify title auto-equipped (first title)
        """
        # 1. Create user with theme at level 9
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(
            user_id=user.id,
            name="Education",
            description="Learning and growth",
            level=9,
            xp=90.0,  # Close to level up (100 needed at level 9)
            xp_to_next_level=100.0 * (1.15**9),  # ~322.9 XP needed
        )
        db_session.add(theme)
        db_session.commit()

        # 2. Create title template requiring theme level >= 10
        title_template = TitleTemplate(
            name="Education Novice",
            description_template="{user_name} has begun their learning journey",
            effect={"type": "xp_multiplier", "scope": "theme", "target": "Education", "value": 1.05},
            rank="D",
            unlock_condition={"type": "theme_level", "theme": "Education", "value": 10},
        )
        db_session.add(title_template)
        db_session.commit()

        # 3. Set up event capture
        event_bus = EventBus()
        captured_events = []

        def capture_title_unlock(payload):
            captured_events.append(payload)

        event_bus.subscribe("title.unlocked", capture_title_unlock)

        # Verify title NOT awarded yet (level 9)
        awarder = TitleAwarder(event_bus)
        initial_titles = awarder.check_user_unlocks(db_session, user.id)
        assert len(initial_titles) == 0, "Should not award title at level 9"

        # 4. Add XP to trigger level 10
        theme.add_xp(theme.xp_to_next_level - theme.xp + 1)  # Just enough to level up
        db_session.commit()
        db_session.refresh(theme)

        assert theme.level == 10, "Theme should now be level 10"

        # 5. Run title awarder
        new_titles = awarder.check_user_unlocks(db_session, user.id)

        # 6. Verify title awarded
        assert len(new_titles) == 1, "Should award one title"
        awarded_title = new_titles[0]
        assert awarded_title.title_template_id == title_template.id
        assert awarded_title.user_id == user.id

        # 7. Verify event emitted
        assert len(captured_events) == 1, "Should emit one title.unlocked event"
        event = captured_events[0]
        assert event["user_id"] == user.id
        assert event["title_name"] == "Education Novice"
        assert event["title_rank"] == "D"

        # 8. Verify auto-equipped (first title)
        assert awarded_title.is_equipped is True, "First title should be auto-equipped"


class TestMultipleTitlesSimultaneous:
    """Test multiple titles unlock at once."""

    def test_multiple_titles_awarded_simultaneously(self, db_session, fake):
        """
        Test scenario where 3 different titles become eligible at once.

        Sets up a user who meets conditions for 3 titles simultaneously
        and verifies all are awarded in one check.
        """
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create theme at level 10 with 1000 XP
        theme = Theme(
            user_id=user.id,
            name="Education",
            level=10,
            xp=1000.0,
        )
        db_session.add(theme)
        db_session.commit()

        # Create skill at Expert rank (level 50)
        skill = Skill(
            user_id=user.id,
            name="Python",
            level=50,
            rank="Expert",
        )
        db_session.add(skill)
        db_session.commit()

        # Create 3 journal entries for journal_count condition
        for i in range(3):
            entry = JournalEntry(
                user_id=user.id,
                content=f"Journal entry {i + 1}",
                entry_type="text",
            )
            db_session.add(entry)
        db_session.commit()

        # Create 3 title templates with different conditions
        templates = [
            TitleTemplate(
                name="Education Master",
                effect={"type": "xp_multiplier", "scope": "theme", "target": "Education", "value": 1.10},
                rank="B",
                unlock_condition={"type": "theme_level", "theme": "Education", "value": 10},
            ),
            TitleTemplate(
                name="Python Expert",
                effect={"type": "xp_multiplier", "scope": "skill", "target": "Python", "value": 1.15},
                rank="A",
                unlock_condition={"type": "skill_rank", "rank": "Expert"},
            ),
            TitleTemplate(
                name="Prolific Writer",
                effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.02},
                rank="C",
                unlock_condition={"type": "journal_count", "value": 3},
            ),
        ]
        for template in templates:
            db_session.add(template)
        db_session.commit()

        # Set up event capture
        event_bus = EventBus()
        captured_events = []
        event_bus.subscribe("title.unlocked", lambda p: captured_events.append(p))

        # Run awarder
        awarder = TitleAwarder(event_bus)
        new_titles = awarder.check_user_unlocks(db_session, user.id)

        # Verify all 3 titles awarded
        assert len(new_titles) == 3, "Should award all 3 titles"
        awarded_names = {db_session.get(TitleTemplate, t.title_template_id).name for t in new_titles}
        assert awarded_names == {"Education Master", "Python Expert", "Prolific Writer"}

        # Verify 3 events emitted
        assert len(captured_events) == 3, "Should emit 3 title.unlocked events"
        event_names = {e["title_name"] for e in captured_events}
        assert event_names == {"Education Master", "Python Expert", "Prolific Writer"}

        # Verify only first title is equipped
        equipped_titles = [t for t in new_titles if t.is_equipped]
        assert len(equipped_titles) == 1, "Only first title should be auto-equipped"


class TestCompoundConditionTitle:
    """Test complex AND/OR condition evaluation."""

    def test_compound_condition_title_unlock_via_and_path(self, db_session, fake):
        """
        Test compound condition: (theme_level >= 10 AND skill_rank == Expert) OR total_xp >= 5000

        This test verifies the AND path to unlock.
        """
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Set up to meet AND condition: theme level 10 + Expert skill
        theme = Theme(
            user_id=user.id,
            name="Education",
            level=10,
            xp=500.0,  # Less than 5000 total
        )
        skill = Skill(
            user_id=user.id,
            name="Python",
            level=50,
            rank="Expert",
        )
        db_session.add_all([theme, skill])
        db_session.commit()

        # Create title with compound condition
        title_template = TitleTemplate(
            name="Scholar Elite",
            effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.25},
            rank="S",
            unlock_condition={
                "type": "or",
                "conditions": [
                    {
                        "type": "and",
                        "conditions": [
                            {"type": "theme_level", "theme": "Education", "value": 10},
                            {"type": "skill_rank", "rank": "Expert"},
                        ],
                    },
                    {"type": "total_xp", "value": 5000},
                ],
            },
        )
        db_session.add(title_template)
        db_session.commit()

        # Run awarder
        event_bus = EventBus()
        captured_events = []
        event_bus.subscribe("title.unlocked", lambda p: captured_events.append(p))

        awarder = TitleAwarder(event_bus)
        new_titles = awarder.check_user_unlocks(db_session, user.id)

        # Verify title awarded via AND path
        assert len(new_titles) == 1
        assert captured_events[0]["title_name"] == "Scholar Elite"

    def test_compound_condition_title_unlock_via_or_path(self, db_session, fake):
        """
        Test compound condition: (theme_level >= 10 AND skill_rank == Expert) OR total_xp >= 5000

        This test verifies the OR path (total_xp >= 5000) to unlock.
        """
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Set up to meet OR condition: total_xp >= 5000 (but NOT AND conditions)
        theme = Theme(
            user_id=user.id,
            name="Education",
            level=5,  # Less than 10
            xp=2500.0,
        )
        theme2 = Theme(
            user_id=user.id,
            name="Health",
            level=5,
            xp=2500.0,  # Total XP = 5000
        )
        skill = Skill(
            user_id=user.id,
            name="Python",
            level=10,
            rank="Amateur",  # Not Expert
        )
        db_session.add_all([theme, theme2, skill])
        db_session.commit()

        # Create title with compound condition
        title_template = TitleTemplate(
            name="Scholar Elite",
            effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.25},
            rank="S",
            unlock_condition={
                "type": "or",
                "conditions": [
                    {
                        "type": "and",
                        "conditions": [
                            {"type": "theme_level", "theme": "Education", "value": 10},
                            {"type": "skill_rank", "rank": "Expert"},
                        ],
                    },
                    {"type": "total_xp", "value": 5000},
                ],
            },
        )
        db_session.add(title_template)
        db_session.commit()

        # Run awarder
        event_bus = EventBus()
        captured_events = []
        event_bus.subscribe("title.unlocked", lambda p: captured_events.append(p))

        awarder = TitleAwarder(event_bus)
        new_titles = awarder.check_user_unlocks(db_session, user.id)

        # Verify title awarded via OR path
        assert len(new_titles) == 1
        assert captured_events[0]["title_name"] == "Scholar Elite"

    def test_compound_condition_not_met(self, db_session, fake):
        """Test that compound condition correctly rejects when neither path is met."""
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Set up to NOT meet either condition
        theme = Theme(
            user_id=user.id,
            name="Education",
            level=5,  # Less than 10
            xp=500.0,  # Total < 5000
        )
        skill = Skill(
            user_id=user.id,
            name="Python",
            level=10,
            rank="Amateur",  # Not Expert
        )
        db_session.add_all([theme, skill])
        db_session.commit()

        # Create title with compound condition
        title_template = TitleTemplate(
            name="Scholar Elite",
            effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.25},
            rank="S",
            unlock_condition={
                "type": "or",
                "conditions": [
                    {
                        "type": "and",
                        "conditions": [
                            {"type": "theme_level", "theme": "Education", "value": 10},
                            {"type": "skill_rank", "rank": "Expert"},
                        ],
                    },
                    {"type": "total_xp", "value": 5000},
                ],
            },
        )
        db_session.add(title_template)
        db_session.commit()

        # Run awarder
        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)
        new_titles = awarder.check_user_unlocks(db_session, user.id)

        # Verify NO title awarded
        assert len(new_titles) == 0


class TestNegativeTitleCorrosion:
    """Test negative title from high corrosion."""

    def test_negative_title_awarded_on_corrosion(self, db_session, fake):
        """
        Test that a debuff title is awarded when theme corrosion reaches 'Rusty'.

        Negative titles reflect neglect and may impose penalties.
        """
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create theme with high corrosion level
        theme = Theme(
            user_id=user.id,
            name="Education",
            level=5,
            corrosion_level="Rusty",  # High corrosion
        )
        db_session.add(theme)
        db_session.commit()

        # Create negative title template
        title_template = TitleTemplate(
            name="The Neglectful",
            description_template="{user_name} has let their studies rust",
            effect={"type": "xp_multiplier", "scope": "theme", "target": "Education", "value": 0.90},  # -10% XP penalty
            rank="D",
            category="negative",
            unlock_condition={"type": "corrosion_level", "theme": "Education", "min_level": "Rusty"},
        )
        db_session.add(title_template)
        db_session.commit()

        # Run awarder
        event_bus = EventBus()
        captured_events = []
        event_bus.subscribe("title.unlocked", lambda p: captured_events.append(p))

        awarder = TitleAwarder(event_bus)
        new_titles = awarder.check_user_unlocks(db_session, user.id)

        # Verify negative title awarded
        assert len(new_titles) == 1
        awarded_title = new_titles[0]
        db_session.refresh(awarded_title)

        assert awarded_title.title_template.name == "The Neglectful"
        assert awarded_title.title_template.category == "negative"

        # Verify event emitted
        assert len(captured_events) == 1
        assert captured_events[0]["title_name"] == "The Neglectful"

    def test_negative_title_not_awarded_fresh_corrosion(self, db_session, fake):
        """Test that negative title is NOT awarded when corrosion is low (Fresh)."""
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create theme with fresh corrosion level
        theme = Theme(
            user_id=user.id,
            name="Education",
            level=5,
            corrosion_level="Fresh",  # Low corrosion
        )
        db_session.add(theme)
        db_session.commit()

        # Create negative title template
        title_template = TitleTemplate(
            name="The Neglectful",
            effect={"type": "xp_multiplier", "scope": "theme", "target": "Education", "value": 0.90},
            rank="D",
            category="negative",
            unlock_condition={"type": "corrosion_level", "theme": "Education", "min_level": "Rusty"},
        )
        db_session.add(title_template)
        db_session.commit()

        # Run awarder
        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)
        new_titles = awarder.check_user_unlocks(db_session, user.id)

        # Verify negative title NOT awarded
        assert len(new_titles) == 0


class TestRealUserJourney:
    """Simulate real user activity over time."""

    def test_title_system_with_real_user_journey(self, db_session, fake):
        """
        Simulate Week 1 of user activity.

        Day 1: Create user, first journal entry
        Day 2-6: More entries, XP accumulates
        Day 7: Check for "Week Warrior" title (journal_streak >= 7)
        Verify title is awarded.
        """
        # Create "Week Warrior" title template first
        title_template = TitleTemplate(
            name="Week Warrior",
            description_template="{user_name} has journaled for a full week",
            effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.10},
            rank="C",
            unlock_condition={"type": "journal_streak", "value": 7},
        )
        db_session.add(title_template)
        db_session.commit()

        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Set up event bus and awarder
        event_bus = EventBus()
        captured_events = []
        event_bus.subscribe("title.unlocked", lambda p: captured_events.append(p))
        awarder = TitleAwarder(event_bus)

        # Simulate 7 days of journaling
        base_date = datetime(2024, 1, 1, 10, 0, 0)

        for day in range(7):
            current_date = base_date + timedelta(days=day)

            # Create journal entry for this day with explicit created_at
            # (freeze_time doesn't intercept SQLAlchemy defaults reliably)
            entry = JournalEntry(
                user_id=user.id,
                content=f"Day {day + 1} journal entry. Reflecting on my progress.",
                entry_type="text",
                created_at=current_date,
            )
            db_session.add(entry)
            db_session.commit()

            # Check for titles each day
            new_titles = awarder.check_user_unlocks(db_session, user.id)

            if day < 6:
                # Days 1-6: Should not unlock Week Warrior yet
                week_warrior_unlocked = any(
                    db_session.get(TitleTemplate, t.title_template_id).name == "Week Warrior"
                    for t in new_titles
                )
                assert not week_warrior_unlocked, f"Week Warrior should not unlock on day {day + 1}"
            else:
                # Day 7: Should unlock Week Warrior
                assert len(new_titles) == 1, "Should unlock Week Warrior on day 7"
                db_session.refresh(new_titles[0])
                assert new_titles[0].title_template.name == "Week Warrior"

        # Verify final state
        assert len(captured_events) == 1
        assert captured_events[0]["title_name"] == "Week Warrior"

        # Verify title is equipped
        user_titles = db_session.query(UserTitle).filter(UserTitle.user_id == user.id).all()
        assert len(user_titles) == 1
        assert user_titles[0].is_equipped is True

    def test_title_not_awarded_twice(self, db_session, fake):
        """Test that the same title is not awarded twice to the same user."""
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create theme that already qualifies
        theme = Theme(
            user_id=user.id,
            name="Education",
            level=15,  # Well above threshold
        )
        db_session.add(theme)
        db_session.commit()

        # Create title template
        title_template = TitleTemplate(
            name="Education Beginner",
            effect={"type": "xp_multiplier", "scope": "theme", "target": "Education", "value": 1.05},
            rank="D",
            unlock_condition={"type": "theme_level", "theme": "Education", "value": 10},
        )
        db_session.add(title_template)
        db_session.commit()

        # Set up event bus and awarder
        event_bus = EventBus()
        captured_events = []
        event_bus.subscribe("title.unlocked", lambda p: captured_events.append(p))
        awarder = TitleAwarder(event_bus)

        # First check - should award title
        first_titles = awarder.check_user_unlocks(db_session, user.id)
        assert len(first_titles) == 1
        assert len(captured_events) == 1

        # Second check - should NOT award title again
        second_titles = awarder.check_user_unlocks(db_session, user.id)
        assert len(second_titles) == 0
        assert len(captured_events) == 1  # No new events

        # Verify only one UserTitle exists
        user_titles = db_session.query(UserTitle).filter(UserTitle.user_id == user.id).all()
        assert len(user_titles) == 1


class TestTitleAwarderEdgeCases:
    """Test edge cases and error handling."""

    def test_title_without_unlock_condition_not_awarded(self, db_session, fake):
        """Test that titles without unlock conditions are not automatically awarded."""
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create title without unlock condition (manual award only)
        title_template = TitleTemplate(
            name="Special Achievement",
            effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.50},
            rank="S",
            unlock_condition=None,  # No auto-unlock
        )
        db_session.add(title_template)
        db_session.commit()

        # Run awarder
        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)
        new_titles = awarder.check_user_unlocks(db_session, user.id)

        # Verify title NOT awarded
        assert len(new_titles) == 0

    def test_manual_award_title(self, db_session, fake):
        """Test manually awarding a title via TitleAwarder.award_title()."""
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create title template
        title_template = TitleTemplate(
            name="Manual Award Title",
            effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.20},
            rank="A",
        )
        db_session.add(title_template)
        db_session.commit()

        # Set up event bus
        event_bus = EventBus()
        captured_events = []
        event_bus.subscribe("title.unlocked", lambda p: captured_events.append(p))

        # Manually award title
        awarder = TitleAwarder(event_bus)
        user_title = awarder.award_title(
            db=db_session,
            user_id=user.id,
            template_id=title_template.id,
            unlock_reason="admin_grant",
        )

        # Verify title awarded
        assert user_title is not None
        assert user_title.user_id == user.id
        assert user_title.title_template_id == title_template.id
        assert user_title.is_equipped is True  # First title auto-equipped

        # Verify event emitted
        assert len(captured_events) == 1
        assert captured_events[0]["title_name"] == "Manual Award Title"

    def test_unknown_condition_type_returns_false(self, db_session, fake):
        """Test that unknown condition types are handled gracefully."""
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create title with unknown condition type
        title_template = TitleTemplate(
            name="Mystery Title",
            effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.10},
            rank="B",
            unlock_condition={"type": "unknown_condition_type", "value": 42},
        )
        db_session.add(title_template)
        db_session.commit()

        # Run awarder
        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)
        new_titles = awarder.check_user_unlocks(db_session, user.id)

        # Verify title NOT awarded (unknown condition treated as not met)
        assert len(new_titles) == 0
