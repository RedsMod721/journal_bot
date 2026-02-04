from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_
from .models import JournalEntry
from tabulate import tabulate
from sqlalchemy.exc import SQLAlchemyError

def safe_query(query_function, *args, **kwargs):
    try:
        return query_function(*args, **kwargs)
    except Exception as e:
        print(f"Query failed: {e}")
        return []

def format_entries(entries):
    if not entries:
        return "No entries found for the given criteria."
    formatted_entries = [{
        "ID": entry.id,
        "Timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "Categories": entry.categories if entry.categories else "None",
        "Content": (entry.content[:100] + "...") if len(entry.content) > 100 else entry.content
    } for entry in entries]
    return tabulate(formatted_entries, headers="keys", tablefmt="grid")

def get_entries_by_date(db: Session, start_date: datetime, end_date: datetime = None):
    if not isinstance(start_date, datetime) or (end_date and not isinstance(end_date, datetime)):
        raise ValueError("start_date and end_date must be valid datetime objects")
    if end_date is None:
        end_date = start_date.replace(hour=23, minute=59, second=59)
    query = lambda: db.query(JournalEntry).filter(JournalEntry.timestamp.between(start_date, end_date)).all()
    return safe_query(query)

def get_entries_by_category(db: Session, categories: list):
    if not categories or not isinstance(categories, list):
        raise ValueError("categories must be a non-empty list of strings")
    query = lambda: db.query(JournalEntry).filter(or_(JournalEntry.categories.like(f'%{category}%') for category in categories)).all()
    return safe_query(query)

def search_entries(db: Session, keyword: str):
    if not keyword or not isinstance(keyword, str):
        raise ValueError("keyword must be a non-empty string")
    try:
        query = lambda: db.query(JournalEntry).filter(JournalEntry.content.ilike(f'%{keyword}%')).all()
        return safe_query(query)
    except SQLAlchemyError as e:
        print(f"Database error: {e}")
        return []

