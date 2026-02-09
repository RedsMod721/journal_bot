"""
Performance tests for the title system.

Tests ensure title checking remains fast even with many templates and user data.
Uses pytest-benchmark if available, otherwise falls back to simple timing.

Run with benchmark:
    pip install pytest-benchmark
    pytest tests/test_performance/ -v --benchmark-only

Run without benchmark:
    pytest tests/test_performance/ -v
"""

import time
from datetime import datetime, timedelta

import pytest

from app.core.events import EventBus
from app.core.titles import TitleAwarder
from app.models.journal_entry import JournalEntry
from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest
from app.models.skill import Skill
from app.models.theme import Theme
from app.models.title import TitleTemplate, UserTitle
from app.models.user import User

# Check if pytest-benchmark is available
try:
    import pytest_benchmark  # noqa: F401

    BENCHMARK_AVAILABLE = True
except ImportError:
    BENCHMARK_AVAILABLE = False


def create_title_templates(db_session, count: int) -> list[TitleTemplate]:
    """Create multiple title templates with various condition types."""
    templates = []
    condition_types = [
        {"type": "theme_level", "theme": "Education", "value": 5},
        {"type": "theme_level", "theme": "Health", "value": 10},
        {"type": "skill_level", "skill": "Python", "value": 15},
        {"type": "skill_rank", "rank": "Expert"},
        {"type": "total_xp", "value": 1000},
        {"type": "journal_count", "value": 50},
        {"type": "journal_streak", "value": 7},
        {"type": "quest_completion_count", "value": 5},
        {"type": "time_based", "days_active": 30},
        {"type": "corrosion_level", "theme": "Education", "min_level": "Rusty"},
        # Compound conditions
        {
            "type": "and",
            "conditions": [
                {"type": "theme_level", "theme": "Education", "value": 10},
                {"type": "skill_rank", "rank": "Advanced"},
            ],
        },
        {
            "type": "or",
            "conditions": [
                {"type": "total_xp", "value": 5000},
                {"type": "journal_count", "value": 100},
            ],
        },
    ]

    for i in range(count):
        condition = condition_types[i % len(condition_types)].copy()
        # Adjust values to make some achievable, some not
        if "value" in condition:
            condition["value"] = (i % 10) + 1

        template = TitleTemplate(
            name=f"Test Title {i + 1}",
            description_template=f"Description for title {i + 1}",
            effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.01},
            rank=["D", "C", "B", "A", "S"][i % 5],
            unlock_condition=condition,
        )
        db_session.add(template)
        templates.append(template)

    db_session.commit()
    return templates


def award_titles_to_user(db_session, user_id: str, templates: list[TitleTemplate], count: int) -> list[UserTitle]:
    """Award a subset of titles to a user."""
    user_titles = []
    for i, template in enumerate(templates[:count]):
        user_title = UserTitle(
            user_id=user_id,
            title_template_id=template.id,
            is_equipped=(i == 0),
        )
        db_session.add(user_title)
        user_titles.append(user_title)

    db_session.commit()
    return user_titles


class TestTitleCheckPerformance:
    """Basic performance tests for title checking."""

    def test_title_check_completes_under_100ms(self, db_session, fake):
        """
        Title checking should be fast even with many templates.

        Setup:
        - Create user
        - Create 50 title templates with various conditions
        - User already owns 10 titles

        Test:
        - Run TitleAwarder.check_user_unlocks()
        - Measure execution time
        - Assert time < 100ms
        """
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create theme and skill for condition evaluation
        theme = Theme(user_id=user.id, name="Education", level=3)
        skill = Skill(user_id=user.id, name="Python", level=5, rank="Amateur")
        db_session.add_all([theme, skill])
        db_session.commit()

        # Create 50 title templates
        templates = create_title_templates(db_session, count=50)

        # Award 10 titles to user (simulating already owned)
        award_titles_to_user(db_session, user.id, templates, count=10)

        # Set up awarder
        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)

        # Warm up (first call may be slower due to lazy loading)
        awarder.check_user_unlocks(db_session, user.id)

        # Measure execution time
        start_time = time.perf_counter()
        result = awarder.check_user_unlocks(db_session, user.id)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Assert performance
        assert elapsed_ms < 100, f"Title check took {elapsed_ms:.2f}ms, expected < 100ms"

        # Verify result is valid (list of UserTitle)
        assert isinstance(result, list)

    def test_title_check_scales_with_user_data(self, db_session, fake):
        """
        Test performance doesn't degrade significantly with user data.

        Setup:
        - Create user with:
          - 10 themes
          - 20 skills
          - 100 journal entries
          - 30 completed quests
        - 100 title templates

        Test:
        - Run check
        - Assert time < 200ms
        """
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create 10 themes
        themes = []
        for i in range(10):
            theme = Theme(
                user_id=user.id,
                name=f"Theme {i + 1}",
                level=i + 1,
                xp=float(i * 100),
            )
            db_session.add(theme)
            themes.append(theme)
        db_session.commit()

        # Create 20 skills
        skills = []
        for i in range(20):
            skill = Skill(
                user_id=user.id,
                theme_id=themes[i % len(themes)].id,
                name=f"Skill {i + 1}",
                level=i + 1,
                rank=["Beginner", "Amateur", "Intermediate", "Advanced"][i % 4],
            )
            db_session.add(skill)
            skills.append(skill)
        db_session.commit()

        # Create 100 journal entries over multiple days
        base_date = datetime(2024, 1, 1, 10, 0, 0)
        for i in range(100):
            entry = JournalEntry(
                user_id=user.id,
                content=f"Journal entry {i + 1} about various topics.",
                entry_type="text",
                created_at=base_date + timedelta(days=i % 50, hours=i % 24),
            )
            db_session.add(entry)
        db_session.commit()

        # Create quest templates and 30 completed quests
        quest_template = MissionQuestTemplate(
            name="Test Quest Template",
            type="daily",
            description_template="A test quest",
            reward_xp=100,
            reward_coins=50,
        )
        db_session.add(quest_template)
        db_session.commit()

        for i in range(30):
            quest = UserMissionQuest(
                user_id=user.id,
                template_id=quest_template.id,
                name=f"Quest Instance {i + 1}",
                status="completed",
                completion_progress=100,
                completion_target=100,
            )
            db_session.add(quest)
        db_session.commit()

        # Create 100 title templates
        templates = create_title_templates(db_session, count=100)

        # Award some titles (20)
        award_titles_to_user(db_session, user.id, templates, count=20)

        # Set up awarder
        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)

        # Warm up
        awarder.check_user_unlocks(db_session, user.id)

        # Measure execution time
        start_time = time.perf_counter()
        result = awarder.check_user_unlocks(db_session, user.id)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Assert performance
        assert elapsed_ms < 200, f"Title check took {elapsed_ms:.2f}ms, expected < 200ms"

        # Verify result is valid
        assert isinstance(result, list)

    def test_title_check_with_many_owned_titles(self, db_session, fake):
        """
        Test performance when user already owns many titles.

        Ensures the owned-title filtering is efficient.
        """
        # Create user
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # Create basic data for condition evaluation
        theme = Theme(user_id=user.id, name="Education", level=1)
        db_session.add(theme)
        db_session.commit()

        # Create 100 title templates
        templates = create_title_templates(db_session, count=100)

        # Award 80 titles to user (most are owned)
        award_titles_to_user(db_session, user.id, templates, count=80)

        # Set up awarder
        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)

        # Warm up
        awarder.check_user_unlocks(db_session, user.id)

        # Measure execution time
        start_time = time.perf_counter()
        result = awarder.check_user_unlocks(db_session, user.id)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Assert performance (should skip owned titles quickly)
        assert elapsed_ms < 100, f"Title check took {elapsed_ms:.2f}ms, expected < 100ms"

        # Should only evaluate 20 unowned titles
        assert isinstance(result, list)


@pytest.mark.skipif(not BENCHMARK_AVAILABLE, reason="pytest-benchmark not installed")
class TestTitleCheckBenchmark:
    """Benchmark tests using pytest-benchmark plugin."""

    def test_title_check_benchmark_basic(self, db_session, fake, benchmark):
        """Benchmark basic title checking with 50 templates."""
        # Setup
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education", level=5)
        skill = Skill(user_id=user.id, name="Python", level=10, rank="Amateur")
        db_session.add_all([theme, skill])
        db_session.commit()

        templates = create_title_templates(db_session, count=50)
        award_titles_to_user(db_session, user.id, templates, count=10)

        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)

        # Benchmark
        result = benchmark(awarder.check_user_unlocks, db_session, user.id)

        # Verify result
        assert isinstance(result, list)

    def test_title_check_benchmark_heavy_load(self, db_session, fake, benchmark):
        """Benchmark title checking with heavy user data."""
        # Setup user with lots of data
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        # 10 themes
        themes = []
        for i in range(10):
            theme = Theme(user_id=user.id, name=f"Theme {i + 1}", level=i + 1)
            db_session.add(theme)
            themes.append(theme)
        db_session.commit()

        # 20 skills
        for i in range(20):
            skill = Skill(
                user_id=user.id,
                theme_id=themes[i % len(themes)].id,
                name=f"Skill {i + 1}",
                level=i,
            )
            db_session.add(skill)
        db_session.commit()

        # 100 journal entries
        base_date = datetime(2024, 1, 1)
        for i in range(100):
            entry = JournalEntry(
                user_id=user.id,
                content=f"Entry {i + 1}",
                entry_type="text",
                created_at=base_date + timedelta(days=i % 50),
            )
            db_session.add(entry)
        db_session.commit()

        # 100 title templates
        templates = create_title_templates(db_session, count=100)
        award_titles_to_user(db_session, user.id, templates, count=20)

        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)

        # Benchmark
        result = benchmark(awarder.check_user_unlocks, db_session, user.id)

        # Verify result
        assert isinstance(result, list)

    def test_title_check_benchmark_compound_conditions(self, db_session, fake, benchmark):
        """Benchmark title checking with many compound conditions."""
        # Setup
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education", level=10)
        skill = Skill(user_id=user.id, name="Python", level=20, rank="Intermediate")
        db_session.add_all([theme, skill])
        db_session.commit()

        # Create 30 templates with complex compound conditions
        templates = []
        for i in range(30):
            condition = {
                "type": "or",
                "conditions": [
                    {
                        "type": "and",
                        "conditions": [
                            {"type": "theme_level", "theme": "Education", "value": i + 5},
                            {"type": "skill_rank", "rank": "Intermediate"},
                        ],
                    },
                    {
                        "type": "and",
                        "conditions": [
                            {"type": "total_xp", "value": (i + 1) * 100},
                            {"type": "journal_count", "value": i + 1},
                        ],
                    },
                ],
            }
            template = TitleTemplate(
                name=f"Compound Title {i + 1}",
                effect={"type": "xp_multiplier", "scope": "all", "target": "all", "value": 1.05},
                rank="B",
                unlock_condition=condition,
            )
            db_session.add(template)
            templates.append(template)
        db_session.commit()

        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)

        # Benchmark
        result = benchmark(awarder.check_user_unlocks, db_session, user.id)

        # Verify result
        assert isinstance(result, list)


class TestPerformanceRegression:
    """Tests to catch performance regressions."""

    def test_multiple_checks_consistent_time(self, db_session, fake):
        """
        Multiple consecutive checks should have consistent timing.

        Ensures no memory leaks or accumulating overhead.
        """
        # Setup
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        theme = Theme(user_id=user.id, name="Education", level=5)
        db_session.add(theme)
        db_session.commit()

        create_title_templates(db_session, count=50)

        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)

        # Run multiple checks and record times
        times = []
        for _ in range(10):
            start = time.perf_counter()
            awarder.check_user_unlocks(db_session, user.id)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        # Calculate statistics
        avg_time = sum(times) / len(times)
        max_time = max(times)

        # First run may be slower, so compare avg vs max of later runs
        later_times = times[2:]  # Skip first 2 warm-up runs
        later_avg = sum(later_times) / len(later_times)
        later_max = max(later_times)

        # Max should not be more than 3x the average (allows for some variance)
        assert later_max < later_avg * 3, f"Inconsistent timing: avg={later_avg:.2f}ms, max={later_max:.2f}ms"

        # Overall should still be fast
        assert avg_time < 100, f"Average time {avg_time:.2f}ms exceeds 100ms threshold"

    def test_empty_templates_fast(self, db_session, fake):
        """
        Checking with no templates should be nearly instant.
        """
        # Setup user with no templates
        user = User(username=fake.user_name(), email=fake.email())
        db_session.add(user)
        db_session.commit()

        event_bus = EventBus()
        awarder = TitleAwarder(event_bus)

        # Measure
        start = time.perf_counter()
        result = awarder.check_user_unlocks(db_session, user.id)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Should be very fast with no templates
        assert elapsed_ms < 10, f"Empty check took {elapsed_ms:.2f}ms, expected < 10ms"
        assert result == []
