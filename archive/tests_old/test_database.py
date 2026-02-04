import sys
import os
from datetime import datetime

# Add the root directory to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import (
    get_db,
    create_entry,
    read_entry_by_date,
    read_entry_by_category,
    search_entries,
    update_entry,
    delete_entry,
)

# Test the database operations
def test_create_entry():
    with next(get_db()) as db:
        new_entry = create_entry(
            db,
            content="This is a test entry about Python testing.",
            categories="test,example",
            timestamp=datetime.utcnow(),
        )
        assert new_entry is not None
        assert new_entry.content == "This is a test entry about Python testing."
        assert new_entry.categories == "test,example"

def test_read_entry_by_date():
    with next(get_db()) as db:
        entries_by_date = read_entry_by_date(db, datetime.now())
        assert isinstance(entries_by_date, list)

def test_read_entry_by_category():
    with next(get_db()) as db:
        entries_by_category = read_entry_by_category(db, "test")
        assert isinstance(entries_by_category, list)

def test_search_entries():
    with next(get_db()) as db:
        entries_by_keyword = search_entries(db, "Python")
        assert isinstance(entries_by_keyword, list)

def test_update_entry():
    with next(get_db()) as db:
        new_entry = create_entry(
            db,
            content="This is a test entry about Python testing.",
            categories="test,example",
            timestamp=datetime.utcnow(),
        )
        updated_entry = update_entry(
            db,
            new_entry.id,
            content="Updated test entry content with more Python.",
            categories="test,updated",
        )
        assert updated_entry is not None
        assert updated_entry.content == "Updated test entry content with more Python."
        assert updated_entry.categories == "test,updated"

def test_delete_entry():
    with next(get_db()) as db:
        new_entry = create_entry(
            db,
            content="This is a test entry about Python testing.",
            categories="test,example",
            timestamp=datetime.utcnow(),
        )
        success = delete_entry(db, new_entry.id)
        assert success is True

def test_read_after_delete():
    with next(get_db()) as db:
        entries_after_delete = read_entry_by_date(db, datetime.now())
        assert isinstance(entries_after_delete, list)

if __name__ == "__main__":
    test_create_entry()
    test_read_entry_by_date()
    test_read_entry_by_category()
    test_search_entries()
    test_update_entry()
    test_delete_entry()
    test_read_after_delete()

