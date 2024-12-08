from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

# Base class for all models
Base = declarative_base()

# JournalEntry model
class JournalEntry(Base):
    __tablename__ = "journal_entries"
    
    # Primary key ID
    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    
    # Timestamp for the entry
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Content of the journal entry
    content = Column(String(5000), nullable=False)
    
    # Comma-separated categories or tags
    categories = Column(String(255), nullable=True)