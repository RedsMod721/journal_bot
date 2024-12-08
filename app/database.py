from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import config  # Assumes DATABASE_URL is defined here
from app.models import Base, JournalEntry


# SQLAlchemy base and session setup
DATABASE_URL = config.DATABASE_URL
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency: Database session generator
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize the database
def init_db():
    """
    Initializes the database by creating all tables.
    """
    Base.metadata.create_all(bind=engine)

# CRUD Operations

# CREATE
def create_entry(db, content: str, categories: str, timestamp: datetime = None):
    """
    Creates a new journal entry in the database.
    :param db: SQLAlchemy session.
    :param content: Text content of the journal entry.
    :param categories: Comma-separated string of categories.
    :param timestamp: Optional datetime for the entry; defaults to now.
    :return: The created JournalEntry object.
    """
    timestamp = timestamp or datetime.utcnow()
    entry = JournalEntry(content=content, categories=categories, timestamp=timestamp)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry

# READ
def read_entry_by_date(db, date: datetime):
    """
    Retrieves all journal entries for a specific date.
    :param db: SQLAlchemy session.
    :param date: The target date as a datetime object.
    :return: List of JournalEntry objects.
    """
    start = datetime(date.year, date.month, date.day)
    end = datetime(date.year, date.month, date.day, 23, 59, 59)
    return db.query(JournalEntry).filter(JournalEntry.timestamp.between(start, end)).all()

def read_entry_by_category(db, category: str):
    """
    Retrieves all journal entries that include a given category.
    :param db: SQLAlchemy session.
    :param category: The target category as a string.
    :return: List of JournalEntry objects.
    """
    return db.query(JournalEntry).filter(JournalEntry.categories.like(f"%{category}%")).all()

def search_entries(db, keyword: str):
    """
    Searches all journal entries for a specific keyword in the content.
    :param db: SQLAlchemy session.
    :param keyword: The keyword to search for.
    :return: List of JournalEntry objects.
    """
    return db.query(JournalEntry).filter(JournalEntry.content.like(f"%{keyword}%")).all()

# UPDATE
def update_entry(db, entry_id: int, content: str = None, categories: str = None):
    """
    Updates an existing journal entry.
    :param db: SQLAlchemy session.
    :param entry_id: ID of the entry to update.
    :param content: New content for the entry (optional).
    :param categories: New categories for the entry (optional).
    :return: The updated JournalEntry object or None if not found.
    """
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if entry:
        if content:
            entry.content = content
        if categories:
            entry.categories = categories
        db.commit()
        db.refresh(entry)
        return entry
    return None

# DELETE
def delete_entry(db, entry_id: int):
    """
    Deletes a journal entry by its ID.
    :param db: SQLAlchemy session.
    :param entry_id: The ID of the journal entry to delete.
    :return: Boolean indicating success or failure.
    """
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).first()
    if entry:
        db.delete(entry)
        db.commit()
        return True
    return False