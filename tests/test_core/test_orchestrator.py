"""Tests for JournalProcessingOrchestrator."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.config_loader import ConfigLoader
from app.core.events import EventBus
from app.core.orchestrator import JournalProcessingOrchestrator, MAX_RETRY_COUNT
from app.models.journal_entry import JournalEntry
from app.models.mission_quest import MissionQuestTemplate, UserMissionQuest
from app.models.theme import Theme
from app.models.skill import Skill
from app.models.title import TitleTemplate, UserTitle


@pytest.fixture
def event_bus() -> EventBus:
    """Create a fresh EventBus for each test."""
    return EventBus()


@pytest.fixture
def config() -> ConfigLoader:
    """Create a ConfigLoader with defaults."""
    return ConfigLoader()


@pytest.fixture
def orchestrator(event_bus, config) -> JournalProcessingOrchestrator:
    """Create an orchestrator instance."""
    return JournalProcessingOrchestrator(event_bus=event_bus, config=config)


@pytest.fixture
def sample_entry(db_session, sample_user) -> JournalEntry:
    """Create a sample journal entry."""
    entry = JournalEntry(
        user_id=sample_user.id,
        content="Today I practiced Python for 30 minutes.",
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    return entry


class TestOrchestratorInitialization:
    """Tests for orchestrator initialization."""

    def test_orchestrator_initializes_with_required_components(
        self, event_bus, config
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        assert orchestrator.xp_calculator is not None
        assert orchestrator.quest_matcher is not None
        assert orchestrator.title_awarder is not None
        assert orchestrator.ai_categorizer is None

    def test_orchestrator_registers_event_listeners(self, event_bus, config) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        # Check that listeners are registered
        assert len(event_bus.get_listeners("journal_entry.created")) >= 1
        assert len(event_bus.get_listeners("xp.awarded")) >= 1
        assert len(event_bus.get_listeners("theme.leveled_up")) >= 1
        assert len(event_bus.get_listeners("skill.leveled_up")) >= 1
        assert len(event_bus.get_listeners("quest.completed")) >= 1

    def test_ai_categorizer_can_be_set(self, orchestrator) -> None:
        mock_categorizer = MagicMock()
        orchestrator.ai_categorizer = mock_categorizer

        assert orchestrator.ai_categorizer is mock_categorizer


class TestProcessEntry:
    """Tests for the process_entry method."""

    def test_process_entry_returns_success_result(
        self,
        db_session,
        orchestrator,
        sample_entry,
    ) -> None:
        result = orchestrator.process_entry(db_session, sample_entry)

        assert result["entry_id"] == sample_entry.id
        assert result["status"] == "completed"
        assert "categories" in result
        assert "xp_summary" in result
        assert "quests_updated" in result
        assert "titles_awarded" in result

    def test_process_entry_updates_status_to_processing_then_completed(
        self,
        db_session,
        orchestrator,
        sample_entry,
    ) -> None:
        # Verify initial status
        assert sample_entry.processing_status == "pending"

        result = orchestrator.process_entry(db_session, sample_entry)

        # Should be completed after processing
        assert sample_entry.processing_status == "completed"

    def test_process_entry_sets_ai_processed_flag(
        self,
        db_session,
        orchestrator,
        sample_entry,
    ) -> None:
        assert sample_entry.ai_processed is False

        orchestrator.process_entry(db_session, sample_entry)

        assert sample_entry.ai_processed is True

    def test_process_entry_populates_ai_categories(
        self,
        db_session,
        orchestrator,
        sample_entry,
    ) -> None:
        orchestrator.process_entry(db_session, sample_entry)

        assert sample_entry.ai_categories == {
            "themes": [],
            "skills": [],
            "sentiment": "neutral",
        }


class TestStubCategorization:
    """Tests for Week 2 stub categorization."""

    def test_stub_categorize_returns_empty_themes(
        self,
        orchestrator,
        sample_entry,
    ) -> None:
        result = orchestrator._stub_categorize(sample_entry)

        assert result["themes"] == []

    def test_stub_categorize_returns_empty_skills(
        self,
        orchestrator,
        sample_entry,
    ) -> None:
        result = orchestrator._stub_categorize(sample_entry)

        assert result["skills"] == []

    def test_stub_categorize_returns_neutral_sentiment(
        self,
        orchestrator,
        sample_entry,
    ) -> None:
        result = orchestrator._stub_categorize(sample_entry)

        assert result["sentiment"] == "neutral"


class TestProcessEntryWithCategories:
    """Tests for processing entries with categories."""

    def test_process_entry_distributes_xp_to_themes(
        self,
        db_session,
        event_bus,
        config,
        sample_user,
        sample_theme,
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        entry = JournalEntry(
            user_id=sample_user.id,
            content="Learning something new.",
        )
        db_session.add(entry)
        db_session.commit()

        # Patch the stub to return categories
        with patch.object(
            orchestrator,
            "_stub_categorize",
            return_value={
                "themes": [{"id": sample_theme.id, "name": sample_theme.name}],
                "skills": [],
                "sentiment": "positive",
            },
        ):
            result = orchestrator.process_entry(db_session, entry)

        assert result["xp_summary"]["total_xp"] > 0
        db_session.refresh(sample_theme)
        assert sample_theme.xp > 0

    def test_process_entry_distributes_xp_to_skills(
        self,
        db_session,
        event_bus,
        config,
        sample_user,
        sample_skill,
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        # Record initial state
        initial_level = sample_skill.level

        entry = JournalEntry(
            user_id=sample_user.id,
            content="Practiced Python today.",
        )
        db_session.add(entry)
        db_session.commit()

        with patch.object(
            orchestrator,
            "_stub_categorize",
            return_value={
                "themes": [],
                "skills": [{"id": sample_skill.id, "name": sample_skill.name}],
                "sentiment": "positive",
            },
        ):
            result = orchestrator.process_entry(db_session, entry)

        # XP was distributed (shown in summary)
        assert result["xp_summary"]["total_xp"] > 0

        # Verify skill received XP - may have leveled up (XP consumed), so check level increase too
        db_session.refresh(sample_skill)
        assert sample_skill.xp > 0 or sample_skill.level > initial_level


class TestQuestMatching:
    """Tests for quest matching integration."""

    def test_process_entry_updates_quest_progress(
        self,
        db_session,
        event_bus,
        config,
        sample_user,
    ) -> None:
        # Create a quest with keyword matching
        template = MissionQuestTemplate(
            name="Exercise Quest",
            completion_condition={"type": "keyword_match", "keywords": ["python"]},
        )
        db_session.add(template)
        db_session.commit()

        quest = UserMissionQuest(
            user_id=sample_user.id,
            template_id=template.id,
            name="Practice Python",
            status="in_progress",
        )
        db_session.add(quest)
        db_session.commit()

        entry = JournalEntry(
            user_id=sample_user.id,
            content="Today I worked on Python programming.",
        )
        db_session.add(entry)
        db_session.commit()

        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        result = orchestrator.process_entry(db_session, entry)

        # Quest should be updated
        assert len(result["quests_updated"]) >= 1

    def test_process_entry_returns_empty_quests_list_when_no_matches(
        self,
        db_session,
        orchestrator,
        sample_entry,
    ) -> None:
        result = orchestrator.process_entry(db_session, sample_entry)

        assert result["quests_updated"] == []


class TestTitleAwarding:
    """Tests for title awarding integration."""

    def test_process_entry_checks_for_title_unlocks(
        self,
        db_session,
        event_bus,
        config,
        sample_user,
    ) -> None:
        # Create a title that unlocks on first journal entry
        template = TitleTemplate(
            name="First Entry",
            description_template="You made your first entry!",
            effect={},
            rank="D",
            unlock_condition={"type": "journal_count", "value": 1},
        )
        db_session.add(template)
        db_session.commit()

        entry = JournalEntry(
            user_id=sample_user.id,
            content="My first entry!",
        )
        db_session.add(entry)
        db_session.commit()

        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        result = orchestrator.process_entry(db_session, entry)

        # Title should be awarded
        assert len(result["titles_awarded"]) >= 1

    def test_process_entry_returns_empty_titles_list_when_none_unlocked(
        self,
        db_session,
        orchestrator,
        sample_entry,
    ) -> None:
        result = orchestrator.process_entry(db_session, sample_entry)

        assert result["titles_awarded"] == []


class TestErrorHandling:
    """Tests for error handling and retry logic."""

    def test_process_entry_handles_xp_distribution_error(
        self,
        db_session,
        event_bus,
        config,
        sample_entry,
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        # Force an error during XP distribution
        with patch.object(
            orchestrator._xp_calculator,
            "process_journal_entry",
            side_effect=ValueError("XP calculation failed"),
        ):
            result = orchestrator.process_entry(db_session, sample_entry)

        assert result["status"] in ("pending", "failed")
        assert "error" in result

    def test_process_entry_increments_retry_count_on_error(
        self,
        db_session,
        event_bus,
        config,
        sample_entry,
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        initial_retry_count = sample_entry.retry_count

        with patch.object(
            orchestrator._xp_calculator,
            "process_journal_entry",
            side_effect=Exception("Test error"),
        ):
            orchestrator.process_entry(db_session, sample_entry)

        assert sample_entry.retry_count == initial_retry_count + 1

    def test_process_entry_sets_last_retry_at_on_error(
        self,
        db_session,
        event_bus,
        config,
        sample_entry,
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        assert sample_entry.last_retry_at is None

        with patch.object(
            orchestrator._xp_calculator,
            "process_journal_entry",
            side_effect=Exception("Test error"),
        ):
            orchestrator.process_entry(db_session, sample_entry)

        assert sample_entry.last_retry_at is not None

    def test_process_entry_stores_error_message(
        self,
        db_session,
        event_bus,
        config,
        sample_entry,
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        with patch.object(
            orchestrator._xp_calculator,
            "process_journal_entry",
            side_effect=Exception("Specific error message"),
        ):
            orchestrator.process_entry(db_session, sample_entry)

        assert "Specific error message" in sample_entry.processing_error

    def test_process_entry_keeps_pending_status_under_max_retries(
        self,
        db_session,
        event_bus,
        config,
        sample_entry,
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        sample_entry.retry_count = MAX_RETRY_COUNT - 2  # One retry left

        with patch.object(
            orchestrator._xp_calculator,
            "process_journal_entry",
            side_effect=Exception("Test error"),
        ):
            orchestrator.process_entry(db_session, sample_entry)

        assert sample_entry.processing_status == "pending"

    def test_process_entry_sets_failed_status_at_max_retries(
        self,
        db_session,
        event_bus,
        config,
        sample_entry,
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        sample_entry.retry_count = MAX_RETRY_COUNT - 1  # This will be the last attempt

        with patch.object(
            orchestrator._xp_calculator,
            "process_journal_entry",
            side_effect=Exception("Test error"),
        ):
            orchestrator.process_entry(db_session, sample_entry)

        assert sample_entry.processing_status == "failed"

    def test_process_entry_truncates_long_error_messages(
        self,
        db_session,
        event_bus,
        config,
        sample_entry,
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        long_error = "x" * 1000  # Longer than 500 char limit

        with patch.object(
            orchestrator._xp_calculator,
            "process_journal_entry",
            side_effect=Exception(long_error),
        ):
            orchestrator.process_entry(db_session, sample_entry)

        assert len(sample_entry.processing_error) <= 500

    def test_voice_entry_with_whitespace_only_content_fails_without_retry(
        self,
        db_session,
        orchestrator,
        sample_user,
    ) -> None:
        entry = JournalEntry(
            user_id=sample_user.id,
            content="   ",
            entry_type="voice",
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        result = orchestrator.process_entry(db_session, entry)

        assert result["status"] == "failed"
        assert entry.processing_status == "failed"
        assert entry.retry_count == 1
        assert "no transcript" in (entry.processing_error or "").lower()

    def test_missing_transcript_sets_failed_even_when_retry_count_low(
        self,
        db_session,
        orchestrator,
        sample_user,
    ) -> None:
        entry = JournalEntry(
            user_id=sample_user.id,
            content="",
            entry_type="voice",
            retry_count=0,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        result = orchestrator.process_entry(db_session, entry)

        assert result["status"] == "failed"
        assert entry.processing_status == "failed"


class TestEventListeners:
    """Tests for event listener behavior."""

    def test_on_entry_created_logs_event(
        self,
        orchestrator,
    ) -> None:
        # Should not raise an exception
        orchestrator._on_entry_created({"entry_id": "test-id", "user_id": "user-id"})

    def test_on_xp_awarded_logs_event(
        self,
        orchestrator,
    ) -> None:
        # Should not raise an exception
        orchestrator._on_xp_awarded({
            "user_id": "user-id",
            "amount": 50,
            "source": "journal",
            "target_type": "theme",
            "target_id": "theme-id",
        })

    def test_on_level_up_logs_event(
        self,
        orchestrator,
    ) -> None:
        # Should not raise an exception
        orchestrator._on_level_up({
            "user_id": "user-id",
            "theme_id": "theme-id",
            "new_level": 5,
            "theme_name": "Education",
        })

    def test_on_quest_completed_logs_event(
        self,
        orchestrator,
    ) -> None:
        # Should not raise an exception
        orchestrator._on_quest_completed({
            "user_id": "user-id",
            "quest_id": "quest-id",
            "quest_name": "Daily Quest",
            "reward_xp": 100,
            "reward_coins": 50,
        })

    def test_event_bus_emits_to_orchestrator_handlers(
        self,
        event_bus,
        config,
    ) -> None:
        handler_called = {"value": False}

        original_handler = JournalProcessingOrchestrator._on_quest_completed

        def patched_handler(self, payload):
            handler_called["value"] = True
            return original_handler(self, payload)

        with patch.object(
            JournalProcessingOrchestrator,
            "_on_quest_completed",
            patched_handler,
        ):
            orchestrator = JournalProcessingOrchestrator(
                event_bus=event_bus,
                config=config,
            )
            event_bus.emit("quest.completed", {
                "user_id": "user-id",
                "quest_id": "quest-id",
                "quest_name": "Test",
                "reward_xp": 0,
                "reward_coins": 0,
            })

        assert handler_called["value"] is True


class TestIntegration:
    """Integration tests for the full processing pipeline."""

    def test_full_pipeline_with_theme_and_skill(
        self,
        db_session,
        event_bus,
        config,
        sample_user,
        sample_theme,
        sample_skill,
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        entry = JournalEntry(
            user_id=sample_user.id,
            content="Great day learning Python!",
        )
        db_session.add(entry)
        db_session.commit()

        # Mock categorization to include theme and skill
        with patch.object(
            orchestrator,
            "_stub_categorize",
            return_value={
                "themes": [{"id": sample_theme.id, "name": sample_theme.name}],
                "skills": [{"id": sample_skill.id, "name": sample_skill.name}],
                "sentiment": "positive",
            },
        ):
            result = orchestrator.process_entry(db_session, entry)

        # Verify complete result
        assert result["status"] == "completed"
        assert result["xp_summary"]["total_xp"] > 0
        assert len(result["xp_summary"]["awards"]) == 2

        # Verify XP was awarded
        db_session.refresh(sample_theme)
        db_session.refresh(sample_skill)
        assert sample_theme.xp > 0
        assert sample_skill.xp > 0

    def test_entry_preserved_after_failure(
        self,
        db_session,
        event_bus,
        config,
        sample_entry,
    ) -> None:
        orchestrator = JournalProcessingOrchestrator(
            event_bus=event_bus,
            config=config,
        )

        original_content = sample_entry.content
        original_id = sample_entry.id

        with patch.object(
            orchestrator._xp_calculator,
            "process_journal_entry",
            side_effect=Exception("Catastrophic failure"),
        ):
            orchestrator.process_entry(db_session, sample_entry)

        # Entry should still exist with original content
        db_session.refresh(sample_entry)
        assert sample_entry.id == original_id
        assert sample_entry.content == original_content
