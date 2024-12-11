from datetime import datetime
import sys
from app.database import create_entry, get_db
from app.categorization import get_categories


def get_user_input() -> str:
    """
    Captures multi-line input from the user for a journal entry.
    Instructions are displayed to guide the user on how to finish the entry.
    Returns the complete input as a single string.
    """
    print("Enter your journal entry below. Press Ctrl+D (or Ctrl+Z on Windows) to finish:\n")
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        print("\nEntry complete.")
    except KeyboardInterrupt:
        print("\nEntry cancelled.")
        return ""
    
    entry_content = "\n".join(lines)
    return entry_content


def process_and_store_input(content: str, categories: str = "") -> None:
    """
    Validates, sanitizes, and stores the user input in the database.
    :param content: The text content of the journal entry.
    :param categories: Optional comma-separated string of categories/tags.
    """
    # Input Validation
    if not content.strip():
        print("Error: Entry is empty. Nothing to save.")
        return

    # Sanitization
    sanitized_content = content.strip()

    # Suggest categories if not provided
    if not categories:
        suggested_categories = get_categories(sanitized_content)
        print(f"Suggested categories: {', '.join(suggested_categories)}")
        categories = input("Please confirm categories (comma-separated) or press Enter to accept suggestions: ")
        if not categories:
            categories = ', '.join(suggested_categories)

    # Store the entry
    try:
        with next(get_db()) as db:
            timestamp = datetime.utcnow()
            new_entry = create_entry(db, content=sanitized_content, categories=categories, timestamp=timestamp)
            print(f"Entry saved successfully with ID: {new_entry.id}")
    except Exception as e:
        print(f"Error saving entry: {e}")