"""
Tests for JournalEntry model.

Tests cover:
- Basic creation and field values
- Default values for entry_type, ai_categories, etc.
- Long content support (5000+ characters)
- User relationship

Following AAA pattern (Arrange, Act, Assert) as per TESTING_GUIDE.md
"""
import pytest  # type: ignore

from app.models.journal_entry import JournalEntry


class TestJournalEntryModel:
    """Tests for JournalEntry model"""

    # =========================================================================
    # BASIC CREATION TESTS
    # =========================================================================

    def test_journal_entry_creation(self, db_session, sample_user):
        """Should create a journal entry with required fields"""
        # Arrange
        content = "Today I worked on my Python project for 2 hours."

        # Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content=content,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.id is not None
        assert len(entry.id) == 36  # UUID format
        assert entry.user_id == sample_user.id
        assert entry.content == content
        assert entry.created_at is not None

    # =========================================================================
    # DEFAULT VALUE TESTS
    # =========================================================================

    def test_journal_entry_default_entry_type(self, db_session, sample_user):
        """New journal entries should default to entry_type='text'"""
        # Arrange & Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Test content",
        )
        db_session.add(entry)
        db_session.commit()

        # Assert
        assert entry.entry_type == "text"

    def test_journal_entry_ai_categories_default_empty(self, db_session, sample_user):
        """New journal entries should have empty ai_categories by default"""
        # Arrange & Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Test content",
        )
        db_session.add(entry)
        db_session.commit()

        # Assert
        assert entry.ai_categories == {}

    def test_journal_entry_all_default_values(self, db_session, sample_user):
        """New journal entries should have correct default values for all fields"""
        # Arrange & Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Test content",
        )
        db_session.add(entry)
        db_session.commit()

        # Assert
        assert entry.entry_type == "text"
        assert entry.ai_categories == {}
        assert entry.ai_suggested_quests == []
        assert entry.ai_processed is False
        assert entry.manual_theme_ids == []
        assert entry.manual_skill_ids == []

    # =========================================================================
    # LONG CONTENT TESTS
    # =========================================================================

    def test_journal_entry_long_content(self, db_session, sample_user):
        """Should handle long content (5000+ characters)"""
        # Arrange - create content with 5500 characters
        long_content = "This is a test. " * 344  # ~5500 chars
        assert len(long_content) > 5000

        # Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content=long_content,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.content == long_content
        assert len(entry.content) > 5000

    def test_journal_entry_very_long_content(self, db_session, sample_user):
        """Should handle very long content (50000+ characters)"""
        # Arrange - create content with ~50000 characters
        very_long_content = "Journal entry text. " * 2501
        assert len(very_long_content) > 50000

        # Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content=very_long_content,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.content == very_long_content
        assert len(entry.content) > 50000

    # =========================================================================
    # ENTRY TYPE TESTS
    # =========================================================================

    def test_journal_entry_voice_transcription_type(self, db_session, sample_user):
        """Should support voice_transcription entry type"""
        # Arrange & Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Transcribed voice content",
            entry_type="voice_transcription",
        )
        db_session.add(entry)
        db_session.commit()

        # Assert
        assert entry.entry_type == "voice_transcription"

    def test_journal_entry_file_upload_type(self, db_session, sample_user):
        """Should support file_upload entry type"""
        # Arrange & Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Content from uploaded file",
            entry_type="file_upload",
        )
        db_session.add(entry)
        db_session.commit()

        # Assert
        assert entry.entry_type == "file_upload"

    # =========================================================================
    # AI FIELDS TESTS
    # =========================================================================

    def test_journal_entry_ai_categories_populated(self, db_session, sample_user):
        """Should store AI-generated categories correctly"""
        # Arrange
        ai_categories = {
            "themes": ["health", "fitness"],
            "skills": ["running", "meal-prep"],
            "sentiment": "positive"
        }

        # Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Went for a run and prepped healthy meals",
            ai_categories=ai_categories,
            ai_processed=True,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.ai_categories == ai_categories
        assert entry.ai_categories["themes"] == ["health", "fitness"]
        assert entry.ai_categories["sentiment"] == "positive"
        assert entry.ai_processed is True

    def test_journal_entry_ai_suggested_quests(self, db_session, sample_user):
        """Should store AI-suggested quests correctly"""
        # Arrange
        suggested_quests = [
            {"name": "Run 5K", "theme": "fitness"},
            {"name": "Meal prep for week", "theme": "health"},
        ]

        # Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Started a new fitness routine",
            ai_suggested_quests=suggested_quests,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.ai_suggested_quests == suggested_quests
        assert len(entry.ai_suggested_quests) == 2

    # =========================================================================
    # MANUAL CATEGORIZATION TESTS
    # =========================================================================

    def test_journal_entry_manual_theme_ids(self, db_session, sample_user):
        """Should store manually selected theme IDs"""
        # Arrange
        theme_ids = ["uuid-1", "uuid-2", "uuid-3"]

        # Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Test content",
            manual_theme_ids=theme_ids,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.manual_theme_ids == theme_ids

    def test_journal_entry_manual_skill_ids(self, db_session, sample_user):
        """Should store manually selected skill IDs"""
        # Arrange
        skill_ids = ["skill-uuid-1", "skill-uuid-2"]

        # Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Practiced Python and JavaScript",
            manual_skill_ids=skill_ids,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.manual_skill_ids == skill_ids

    # =========================================================================
    # RELATIONSHIP TESTS
    # =========================================================================

    def test_journal_entry_user_relationship_bidirectional(
        self, db_session, sample_user
    ):
        """JournalEntry should have bidirectional relationship with user"""
        # Arrange & Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Test journal entry",
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(sample_user)

        # Assert
        assert entry.user is not None
        assert entry.user.id == sample_user.id
        assert entry in sample_user.journal_entries

    def test_user_deletion_cascades_to_journal_entries(self, db_session, sample_user):
        """Deleting user should cascade delete all journal entries"""
        # Arrange
        entry1 = JournalEntry(user_id=sample_user.id, content="Entry 1")
        entry2 = JournalEntry(user_id=sample_user.id, content="Entry 2")
        db_session.add_all([entry1, entry2])
        db_session.commit()
        user_id = sample_user.id

        # Act
        db_session.delete(sample_user)
        db_session.commit()

        # Assert
        remaining_entries = db_session.query(JournalEntry).filter(
            JournalEntry.user_id == user_id
        ).all()
        assert len(remaining_entries) == 0

    # =========================================================================
    # REPR AND UUID TESTS
    # =========================================================================

    def test_journal_entry_uuid_generation(self, db_session, sample_user):
        """JournalEntry should auto-generate UUID for primary key"""
        # Arrange & Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Test content",
        )
        db_session.add(entry)
        db_session.commit()

        # Assert
        assert entry.id is not None
        assert len(entry.id) == 36  # UUID format
        assert entry.id.count("-") == 4

    def test_journal_entry_repr_short_content(self, db_session, sample_user):
        """JournalEntry __repr__ should show truncated content preview"""
        # Arrange
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Short entry",
            entry_type="text",
        )
        db_session.add(entry)
        db_session.commit()

        # Act
        repr_str = repr(entry)

        # Assert
        assert "JournalEntry" in repr_str
        assert "text" in repr_str
        assert "Short entry" in repr_str

    def test_journal_entry_repr_long_content_truncated(self, db_session, sample_user):
        """JournalEntry __repr__ should truncate long content with ellipsis"""
        # Arrange
        long_content = "A" * 100
        entry = JournalEntry(
            user_id=sample_user.id,
            content=long_content,
            entry_type="text",
        )
        db_session.add(entry)
        db_session.commit()

        # Act
        repr_str = repr(entry)

        # Assert
        assert "..." in repr_str
        assert len(repr_str) < len(long_content) + 50  # Much shorter than full content

    # =========================================================================
    # DEFAULT MUTABILITY AND EDGE CASES
    # =========================================================================

    def test_journal_entry_default_fields_are_not_shared(self, db_session, sample_user):
        """Default JSON/list fields should not be shared across instances"""
        # Arrange
        entry1 = JournalEntry(user_id=sample_user.id, content="Entry 1")
        entry2 = JournalEntry(user_id=sample_user.id, content="Entry 2")
        db_session.add_all([entry1, entry2])
        db_session.commit()
        db_session.refresh(entry1)
        db_session.refresh(entry2)

        # Act - mutate entry1 defaults
        entry1.ai_categories["mood"] = "focused"
        entry1.ai_suggested_quests.append({"name": "Test Quest"})
        entry1.manual_theme_ids.append("theme-1")
        entry1.manual_skill_ids.append("skill-1")

        # Assert - entry2 remains default
        assert entry2.ai_categories == {}
        assert entry2.ai_suggested_quests == []
        assert entry2.manual_theme_ids == []
        assert entry2.manual_skill_ids == []

    def test_journal_entry_repr_boundary_lengths(self, db_session, sample_user):
        """__repr__ should only truncate when content exceeds 30 chars"""
        # Arrange
        content_30 = "A" * 30
        content_31 = "B" * 31

        entry_30 = JournalEntry(user_id=sample_user.id, content=content_30)
        entry_31 = JournalEntry(user_id=sample_user.id, content=content_31)
        db_session.add_all([entry_30, entry_31])
        db_session.commit()

        # Act
        repr_30 = repr(entry_30)
        repr_31 = repr(entry_31)

        # Assert
        assert "..." not in repr_30
        assert "..." in repr_31

    def test_journal_entry_ai_processed_false_with_ai_data(self, db_session, sample_user):
        """AI data should persist even when ai_processed is False"""
        # Arrange
        ai_categories = {"themes": ["Work"], "score": 0.7}
        suggested = [{"name": "Follow up"}]

        # Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Test content",
            ai_categories=ai_categories,
            ai_suggested_quests=suggested,
            ai_processed=False,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.ai_processed is False
        assert entry.ai_categories == ai_categories
        assert entry.ai_suggested_quests == suggested

    def test_journal_entry_entry_type_allows_custom_value(self, db_session, sample_user):
        """entry_type should accept custom string values"""
        # Arrange & Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Custom type entry",
            entry_type="custom_type",
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.entry_type == "custom_type"

    def test_journal_entry_empty_content_allowed(self, db_session, sample_user):
        """Empty content should be stored (no validation enforced)"""
        # Arrange & Act
        entry = JournalEntry(user_id=sample_user.id, content="")
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.content == ""

    def test_journal_entry_ai_categories_non_string_values(self, db_session, sample_user):
        """AI categories should store non-string JSON values"""
        # Arrange
        ai_categories = {"score": 0.85, "count": 2, "nested": {"ok": True}}

        # Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Test content",
            ai_categories=ai_categories,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.ai_categories == ai_categories

    def test_journal_entry_manual_ids_mixed_values(self, db_session, sample_user):
        """Manual IDs should accept mixed string values"""
        # Arrange
        theme_ids = ["theme-uuid-1", "theme-uuid-2"]
        skill_ids = ["skill-uuid-1", "skill-uuid-2", "skill-uuid-3"]

        # Act
        entry = JournalEntry(
            user_id=sample_user.id,
            content="Test content",
            manual_theme_ids=theme_ids,
            manual_skill_ids=skill_ids,
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        # Assert
        assert entry.manual_theme_ids == theme_ids
        assert entry.manual_skill_ids == skill_ids
