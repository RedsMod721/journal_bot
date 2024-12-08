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
def test_database():
    # Get a database session
    with next(get_db()) as db:
        # CREATE
        print("Testing CREATE...")
        new_entry = create_entry(
            db,
            content="This is a test entry about Python testing.",
            categories="test,example",
            timestamp=datetime.utcnow(),
        )
        print("Created Entry:", new_entry)

        # READ BY DATE
        print("\nTesting READ by Date...")
        entries_by_date = read_entry_by_date(db, datetime.now())
        print("Entries by Date:", entries_by_date)

        # READ BY CATEGORY
        print("\nTesting READ by Category...")
        entries_by_category = read_entry_by_category(db, "test")
        print("Entries by Category:", entries_by_category)

        # SEARCH BY KEYWORD
        print("\nTesting SEARCH by Keyword...")
        entries_by_keyword = search_entries(db, "Python")
        print("Entries by Keyword:", entries_by_keyword)

        # UPDATE
        print("\nTesting UPDATE...")
        updated_entry = update_entry(
            db,
            new_entry.id,
            content="Updated test entry content with more Python.",
            categories="test,updated",
        )
        print("Updated Entry:", updated_entry)

        # DELETE
        print("\nTesting DELETE...")
        success = delete_entry(db, new_entry.id)
        print("Entry Deleted:", success)

        # READ AFTER DELETE
        print("\nTesting READ after DELETE...")
        entries_after_delete = read_entry_by_date(db, datetime.now())
        print("Entries after Delete:", entries_after_delete)


if __name__ == "__main__":
    test_database()
