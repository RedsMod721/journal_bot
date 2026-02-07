"""
JournalEntry Pydantic schemas for Status Window API.

This module defines schemas for JournalEntry data validation and serialization:
- JournalEntryBase: Shared fields for journal entry data
- JournalEntryCreate: Schema for creating new entries (POST requests)
- JournalEntryUpdate: Schema for partial entry updates (PATCH requests)
- JournalEntryResponse: Schema for API responses with full entry data

Journal entries are the primary input mechanism - users submit text that
gets processed by AI to extract themes, skills, and quest progress.
"""
from datetime import datetime

from pydantic import ConfigDict, Field

from app.schemas.base import BaseSchema, UUIDStr


class JournalEntryBase(BaseSchema):
    """
    Base schema with shared journal entry fields.

    Used as a parent class for JournalEntryCreate and JournalEntryResponse.
    Contains core fields that define a journal entry.

    Attributes:
        content: The journal text content (must be non-empty)
        entry_type: Type of entry (text, voice_transcription, file_upload)
    """

    content: str = Field(min_length=1)
    entry_type: str = Field(default="text", max_length=50)


class JournalEntryCreate(JournalEntryBase):
    """
    Schema for creating a new journal entry.

    Used for POST /journal endpoint. Inherits content and entry_type
    from JournalEntryBase. Requires user_id for ownership.

    Attributes:
        user_id: UUID of the user who owns this entry

    Example:
        {
            "content": "Today I went for a 5km run...",
            "entry_type": "text",
            "user_id": "123e4567-e89b-12d3-a456-426614174000"
        }
    """

    user_id: UUIDStr


class JournalEntryUpdate(BaseSchema):
    """
    Schema for partial journal entry updates.

    Used for PATCH /journal/{id} endpoint. All fields are optional
    to allow partial updates of entry attributes.

    Attributes:
        content: Optional new content
        ai_categories: Optional AI-detected categories
        ai_suggested_quests: Optional AI-suggested quests
        ai_processed: Optional processing flag
        manual_theme_ids: Optional user-selected theme IDs
        manual_skill_ids: Optional user-selected skill IDs

    Example:
        {
            "ai_categories": {"themes": ["health"], "sentiment": "positive"},
            "ai_processed": true
        }
    """

    content: str | None = Field(default=None, min_length=1)
    ai_categories: dict | None = None
    ai_suggested_quests: list | None = None
    ai_processed: bool | None = None
    manual_theme_ids: list | None = None
    manual_skill_ids: list | None = None


class JournalEntryResponse(JournalEntryBase):
    """
    Schema for journal entry API responses.

    Includes all entry fields returned by the API, including
    auto-generated fields like id and AI processing results.

    Attributes:
        id: Unique UUID identifier
        user_id: UUID of the owning user
        created_at: Timestamp of entry creation
        ai_categories: AI-detected categories (themes, skills, sentiment)
        ai_suggested_quests: AI-suggested quests based on content
        ai_processed: Whether AI has processed this entry

    Example:
        {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "user_id": "987fcdeb-51a2-3bc4-d567-890123456789",
            "content": "Today I went for a 5km run...",
            "entry_type": "text",
            "created_at": "2025-01-15T10:30:00",
            "ai_categories": {"themes": ["health"], "sentiment": "positive"},
            "ai_suggested_quests": [],
            "ai_processed": true
        }
    """

    id: UUIDStr
    user_id: UUIDStr
    created_at: datetime
    ai_categories: dict
    ai_suggested_quests: list
    ai_processed: bool

    model_config = ConfigDict(from_attributes=True)
