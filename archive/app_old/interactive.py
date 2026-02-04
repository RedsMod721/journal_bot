from app.input_handler import process_and_store_input
from app.retrieval import get_entries_by_date, get_entries_by_category, search_entries
from app.display import display_entries
from app.validators import validate_date_range, validate_categories, validate_keyword

def interactive_mode():
    while True:
        print("Menu:")
        print("1. Add a new journal entry")
        print("2. View journal entries by date")
        print("3. View journal entries by category")
        print("4. Search journal entries by keyword")
        print("5. Exit")

        choice = input("Enter your choice: ").strip()

        if choice == "1":
            content = input("Enter your journal entry: ").strip()
            categories = input("Enter categories (comma-separated): ").strip()
            process_and_store_input(content, categories)
        elif choice == "2":
            view_date = input("Enter the date or date range (e.g., 'YYYY-MM-DD' or 'YYYY-MM-DD,YYYY-MM-DD'): ").strip()
            start_date, end_date = validate_date_range(view_date)
            if start_date and end_date:
                entries = get_entries_by_date(start_date, end_date)
                display_entries(entries)
        elif choice == "3":
            view_category = input("Enter the category: ").strip()
            categories = validate_categories(view_category)
            if categories:
                entries = get_entries_by_category(categories)
                display_entries(entries)
        elif choice == "4":
            search_keyword = input("Enter the keyword: ").strip()
            keyword = validate_keyword(search_keyword)
            if keyword:
                entries = search_entries(keyword)
                display_entries(entries)
        elif choice == "5":
            break
        else:
            print("Invalid choice. Please enter a number from 1 to 5.")
