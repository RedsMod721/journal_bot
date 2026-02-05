"""
JournalEntry model for Status Window API.

Journal entries are the primary input mechanism for the system.
Users submit text (or voice transcriptions) that get processed by AI
to extract themes, skills, and quest progress.

AI processing populates:
- ai_categories: Detected themes, skills, sentiment
- ai_suggested_quests: New quests based on entry content
- ai_processed: Flag indicating processing completion

Manual categorization fields allow user override:
- manual_theme_ids: User-selected themes
- manual_skill_ids: User-selected skills
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship

from app.utils.database import Base


class JournalEntry(Base):
    """
    JournalEntry model representing a user's journal submission.

    Attributes:
        id: Unique identifier (UUID string)
        user_id: Foreign key to the user who created the entry
        content: The actual journal text content (supports long text)
        entry_type: Type of entry - text, voice_transcription, or file_upload
        created_at: Timestamp of entry creation
        ai_categories: AI-detected categories (themes, skills, sentiment)
        ai_suggested_quests: AI-suggested new quests based on content
        ai_processed: Whether AI has processed this entry
        manual_theme_ids: User-manually-selected theme IDs
        manual_skill_ids: User-manually-selected skill IDs

    Relationships:
        user: The User who created this entry (many-to-one)
    """

    __tablename__ = "journal_entries"

    # Primary key - UUID stored as string for SQLite compatibility
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )

    # Foreign key to user
    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Journal content - using Text for long content support
    content = Column(Text, nullable=False)

    # Entry type: text, voice_transcription, file_upload
    entry_type = Column(String(50), default="text", nullable=False)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # AI-generated fields
    # Stores: {"themes": [...], "skills": [...], "sentiment": "..."}
    ai_categories = Column(JSON, default=dict, nullable=False)

    # AI-suggested quests based on entry content
    ai_suggested_quests = Column(JSON, default=list, nullable=False)

    # Flag indicating AI has processed this entry
    ai_processed = Column(Boolean, default=False, nullable=False)

    # Manual categorization (user override)
    manual_theme_ids = Column(JSON, default=list, nullable=False)
    manual_skill_ids = Column(JSON, default=list, nullable=False)

    # =========================================================================
    # RELATIONSHIPS
    # =========================================================================

    user = relationship("User", back_populates="journal_entries")

    def __repr__(self) -> str:
        """String representation for debugging."""
        content_preview = (
            self.content[:30] + "..." if len(self.content) > 30 else self.content
        )
        return f"<JournalEntry {self.entry_type}: '{content_preview}'>"
