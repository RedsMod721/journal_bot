"""
Tests for JournalEntry CRUD operations.

This module tests all CRUD functions in app/crud/journal.py:
- create_journal_entry: Creating entries
- get_journal_entry: Retrieving by ID
- get_user_journal_entries: Pagination and ordering
- get_recent_entries: Time-based filtering
- update_journal_entry: Partial updates
- mark_as_ai_processed: AI processing flag and categories
- delete_journal_entry: Removal behavior

Uses db_session and sample_user fixtures from conftest.py.
"""
from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time
from pydantic import ValidationError

from app.crud.journal import (
    create_journal_entry,
    delete_journal_entry,
    get_journal_entry,
    get_recent_entries,
    get_user_journal_entries,
    mark_as_ai_processed,
    update_journal_entry,
)
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate


class TestJournalCRUD:
    """Comprehensive tests for JournalEntry CRUD operations."""

    # =========================================================================
    # CREATE TESTS
    # =========================================================================

    def test_create_journal_entry(self, db_session, sample_user):
        """Should create journal entry with valid data."""
        # Arrange
        entry_data = JournalEntryCreate(
            content="Today I went for a run",
            entry_type="text",
            user_id=sample_user.id,
        )

        # Act
        result = create_journal_entry(db_session, entry_data)

        # Assert
        assert result is not None
        assert result.id is not None
        assert len(result.id) == 36
        assert result.user_id == sample_user.id
        assert result.content == "Today I went for a run"
        assert result.entry_type == "text"
        assert result.created_at is not None
        assert result.ai_categories == {}
        assert result.ai_suggested_quests == []
        assert result.ai_processed is False
        assert result.manual_theme_ids == []
        assert result.manual_skill_ids == []

    def test_create_journal_entry_defaults(self, db_session, sample_user):
        """Should apply default entry_type when not provided."""
        # Arrange
        entry_data = JournalEntryCreate(
            content="Default entry type",
            user_id=sample_user.id,
        )

        # Act
        result = create_journal_entry(db_session, entry_data)

        # Assert
        assert result.entry_type == "text"

    def test_create_journal_entry_invalid_content_raises_validation_error(self, sample_user):
        """Should raise ValidationError for empty content."""
        # Act & Assert
        with pytest.raises(ValidationError):
            JournalEntryCreate(content="", user_id=sample_user.id)

    def test_create_journal_entry_invalid_user_id_raises_validation_error(self):
        """Should raise ValidationError for invalid user_id UUID."""
        # Act & Assert
        with pytest.raises(ValidationError):
            JournalEntryCreate(content="Hello", user_id="not-a-uuid")

    # =========================================================================
    # READ TESTS
    # =========================================================================

    def test_get_journal_entry_by_id(self, db_session, sample_user):
        """Should return entry when ID exists."""
        # Arrange
        entry = create_journal_entry(
            db_session,
            JournalEntryCreate(content="Fetch me", user_id=sample_user.id),
        )

        # Act
        result = get_journal_entry(db_session, entry.id)

        # Assert
        assert result is not None
        assert result.id == entry.id

    def test_get_journal_entry_not_found(self, db_session):
        """Should return None when ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = get_journal_entry(db_session, non_existent_id)

        # Assert
        assert result is None

    # =========================================================================
    # LIST/PAGINATION TESTS
    # =========================================================================

    def test_get_user_journal_entries_pagination(self, db_session, sample_user):
        """Should return paginated list of entries."""
        # Arrange
        for i in range(5):
            create_journal_entry(
                db_session,
                JournalEntryCreate(content=f"Entry {i}", user_id=sample_user.id),
            )

        # Act
        page1 = get_user_journal_entries(db_session, sample_user.id, skip=0, limit=3)
        page2 = get_user_journal_entries(db_session, sample_user.id, skip=3, limit=3)

        # Assert
        assert len(page1) == 3
        assert len(page2) == 2

    def test_get_user_journal_entries_ordered_by_newest(self, db_session, sample_user):
        """Should return entries ordered by created_at descending."""
        # Arrange
        with freeze_time("2026-02-01 10:00:00"):
            e1 = create_journal_entry(
                db_session,
                JournalEntryCreate(content="Oldest", user_id=sample_user.id),
            )
        with freeze_time("2026-02-02 10:00:00"):
            e2 = create_journal_entry(
                db_session,
                JournalEntryCreate(content="Middle", user_id=sample_user.id),
            )
        with freeze_time("2026-02-03 10:00:00"):
            e3 = create_journal_entry(
                db_session,
                JournalEntryCreate(content="Newest", user_id=sample_user.id),
            )

        # Act
        result = get_user_journal_entries(db_session, sample_user.id)

        # Assert
        assert [r.id for r in result[:3]] == [e3.id, e2.id, e1.id]

    def test_get_user_journal_entries_empty(self, db_session, sample_user):
        """Should return empty list when user has no entries."""
        # Act
        result = get_user_journal_entries(db_session, sample_user.id)

        # Assert
        assert result == []

    # =========================================================================
    # RECENT ENTRIES TESTS
    # =========================================================================

    def test_get_recent_entries_last_7_days(self, db_session, sample_user):
        """Should return entries from the last 7 days only."""
        # Arrange
        old = create_journal_entry(
            db_session,
            JournalEntryCreate(content="Old", user_id=sample_user.id),
        )
        recent = create_journal_entry(
            db_session,
            JournalEntryCreate(content="Recent", user_id=sample_user.id),
        )
        now = create_journal_entry(
            db_session,
            JournalEntryCreate(content="Now", user_id=sample_user.id),
        )

        old.created_at = datetime(2026, 1, 30, 10, 0, 0)
        recent.created_at = datetime(2026, 2, 6, 10, 0, 0)
        now.created_at = datetime(2026, 2, 8, 10, 0, 0)
        db_session.commit()

        # Act
        with freeze_time("2026-02-08 12:00:00"):
            result = get_recent_entries(db_session, sample_user.id, days=7)

        # Assert
        ids = {r.id for r in result}
        assert recent.id in ids
        assert now.id in ids
        assert len(ids) == 2

    def test_get_recent_entries_empty(self, db_session, sample_user):
        """Should return empty list when no recent entries exist."""
        # Arrange
        entry = create_journal_entry(
            db_session,
            JournalEntryCreate(content="Old", user_id=sample_user.id),
        )
        entry.created_at = datetime(2026, 2, 1, 10, 0, 0)
        db_session.commit()

        # Act
        with freeze_time("2026-02-10 10:00:00"):
            result = get_recent_entries(db_session, sample_user.id, days=3)

        # Assert
        assert result == []

    # =========================================================================
    # UPDATE TESTS
    # =========================================================================

    def test_update_journal_entry_content(self, db_session, sample_user):
        """Should update entry content."""
        # Arrange
        entry = create_journal_entry(
            db_session,
            JournalEntryCreate(content="Original", user_id=sample_user.id),
        )

        # Act
        update = JournalEntryUpdate(content="Updated")
        result = update_journal_entry(db_session, entry.id, update)

        # Assert
        assert result is not None
        assert result.content == "Updated"

    def test_update_journal_entry_ai_fields(self, db_session, sample_user):
        """Should update AI and manual fields."""
        # Arrange
        entry = create_journal_entry(
            db_session,
            JournalEntryCreate(content="AI", user_id=sample_user.id),
        )

        # Act
        update = JournalEntryUpdate(
            ai_categories={"themes": ["health"], "sentiment": "positive"},
            ai_suggested_quests=[{"name": "Quest"}],
            ai_processed=True,
            manual_theme_ids=["theme1"],
            manual_skill_ids=["skill1"],
        )
        result = update_journal_entry(db_session, entry.id, update)

        # Assert
        assert result is not None
        assert result.ai_categories["sentiment"] == "positive"
        assert result.ai_suggested_quests[0]["name"] == "Quest"
        assert result.ai_processed is True
        assert result.manual_theme_ids == ["theme1"]
        assert result.manual_skill_ids == ["skill1"]

    def test_update_journal_entry_invalid_content_raises_validation_error(self):
        """Should raise ValidationError for empty content."""
        # Act & Assert
        with pytest.raises(ValidationError):
            JournalEntryUpdate(content="")

    def test_update_journal_entry_not_found(self, db_session):
        """Should return None when entry ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        update = JournalEntryUpdate(content="Updated")
        result = update_journal_entry(db_session, non_existent_id, update)

        # Assert
        assert result is None

    # =========================================================================
    # AI PROCESSING TESTS
    # =========================================================================

    def test_mark_as_ai_processed_updates_fields(self, db_session, sample_user):
        """Should set ai_processed to True and update ai_categories."""
        # Arrange
        entry = create_journal_entry(
            db_session,
            JournalEntryCreate(content="Process me", user_id=sample_user.id),
        )
        categories = {"themes": ["health"], "sentiment": "neutral"}

        # Act
        result = mark_as_ai_processed(db_session, entry.id, categories)

        # Assert
        assert result is not None
        assert result.ai_processed is True
        assert result.ai_categories == categories

    def test_mark_as_ai_processed_not_found(self, db_session):
        """Should return None when entry ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = mark_as_ai_processed(db_session, non_existent_id, {"themes": []})

        # Assert
        assert result is None

    # =========================================================================
    # DELETE TESTS
    # =========================================================================

    def test_delete_journal_entry(self, db_session, sample_user):
        """Should delete entry and return True."""
        # Arrange
        entry = create_journal_entry(
            db_session,
            JournalEntryCreate(content="Delete", user_id=sample_user.id),
        )

        # Act
        result = delete_journal_entry(db_session, entry.id)

        # Assert
        assert result is True
        assert get_journal_entry(db_session, entry.id) is None

    def test_delete_journal_entry_not_found(self, db_session):
        """Should return False when entry ID does not exist."""
        # Arrange
        non_existent_id = "00000000-0000-0000-0000-000000000000"

        # Act
        result = delete_journal_entry(db_session, non_existent_id)

        # Assert
        assert result is False

    def test_delete_journal_entry_already_deleted_returns_false(self, db_session, sample_user):
        """Should return False when deleting entry twice."""
        # Arrange
        entry = create_journal_entry(
            db_session,
            JournalEntryCreate(content="Delete Twice", user_id=sample_user.id),
        )

        # Act
        first_result = delete_journal_entry(db_session, entry.id)
        second_result = delete_journal_entry(db_session, entry.id)

        # Assert
        assert first_result is True
        assert second_result is False
