"""
CRUD operations for JournalEntry model.

This module provides database operations for JournalEntry management:
- Create: Create new journal entries
- Read: Get entries by ID, user, or date range
- Update: Modify entry content and AI processing results
- Delete: Remove entries

All functions take a SQLAlchemy Session as the first argument
and return JournalEntry model instances or None for not-found cases.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.journal_entry import JournalEntry
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate


def create_journal_entry(db: Session, journal: JournalEntryCreate) -> JournalEntry:
    """
    Create a new journal entry in the database.

    Args:
        db: Database session
        journal: JournalEntryCreate schema with content and user_id

    Returns:
        JournalEntry: The created entry instance

    Example:
        entry_data = JournalEntryCreate(
            content="Today I went for a 5km run...",
            user_id="123e4567-..."
        )
        entry = create_journal_entry(db, entry_data)
    """
    db_entry = JournalEntry(
        user_id=journal.user_id,
        content=journal.content,
        entry_type=journal.entry_type,
    )
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    return db_entry


def get_journal_entry(db: Session, entry_id: str) -> JournalEntry | None:
    """
    Retrieve a journal entry by its ID.

    Args:
        db: Database session
        entry_id: The UUID string of the entry

    Returns:
        JournalEntry: The entry instance if found
        None: If no entry exists with that ID
    """
    return db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()


def get_user_journal_entries(
    db: Session, user_id: str, skip: int = 0, limit: int = 50
) -> list[JournalEntry]:
    """
    Retrieve journal entries for a user with pagination.

    Returns entries ordered by created_at descending (newest first).

    Args:
        db: Database session
        user_id: The UUID string of the user
        skip: Number of records to skip (offset)
        limit: Maximum number of records to return

    Returns:
        list[JournalEntry]: List of entry instances for the user
    """
    return (
        db.query(JournalEntry)
        .filter(JournalEntry.user_id == user_id)
        .order_by(JournalEntry.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_recent_entries(
    db: Session, user_id: str, days: int = 7
) -> list[JournalEntry]:
    """
    Retrieve journal entries from the last N days.

    Returns entries ordered by created_at descending (newest first).

    Args:
        db: Database session
        user_id: The UUID string of the user
        days: Number of days to look back (default 7)

    Returns:
        list[JournalEntry]: List of recent entry instances

    Example:
        # Get entries from the last week
        entries = get_recent_entries(db, user_id, days=7)
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    return (
        db.query(JournalEntry)
        .filter(JournalEntry.user_id == user_id)
        .filter(JournalEntry.created_at >= cutoff_date)
        .order_by(JournalEntry.created_at.desc())
        .all()
    )


def update_journal_entry(
    db: Session, entry_id: str, entry_update: JournalEntryUpdate
) -> JournalEntry | None:
    """
    Update a journal entry's attributes.

    Only updates fields that are explicitly set in the update schema.
    Uses exclude_unset=True to allow partial updates.

    Args:
        db: Database session
        entry_id: The UUID string of the entry to update
        entry_update: JournalEntryUpdate schema with fields to update

    Returns:
        JournalEntry: The updated entry instance
        None: If no entry exists with that ID

    Example:
        update = JournalEntryUpdate(content="Updated content...")
        entry = update_journal_entry(db, entry_id, update)
    """
    db_entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if db_entry is None:
        return None

    update_data = entry_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_entry, field, value)

    db.commit()
    db.refresh(db_entry)
    return db_entry


def mark_as_ai_processed(
    db: Session, entry_id: str, ai_categories: dict
) -> JournalEntry | None:
    """
    Mark a journal entry as processed by AI.

    Sets ai_processed to True and updates ai_categories with
    the AI-detected themes, skills, and sentiment.

    Args:
        db: Database session
        entry_id: The UUID string of the entry
        ai_categories: Dict with AI results (themes, skills, sentiment)

    Returns:
        JournalEntry: The updated entry instance
        None: If no entry exists with that ID

    Example:
        categories = {
            "themes": ["health", "fitness"],
            "skills": ["running"],
            "sentiment": "positive"
        }
        entry = mark_as_ai_processed(db, entry_id, categories)
    """
    db_entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if db_entry is None:
        return None

    db_entry.ai_processed = True
    db_entry.ai_categories = ai_categories
    db.commit()
    db.refresh(db_entry)
    return db_entry


def delete_journal_entry(db: Session, entry_id: str) -> bool:
    """
    Delete a journal entry.

    Args:
        db: Database session
        entry_id: The UUID string of the entry to delete

    Returns:
        True: If the entry was successfully deleted
        False: If no entry exists with that ID
    """
    db_entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if db_entry is None:
        return False

    db.delete(db_entry)
    db.commit()
    return True
