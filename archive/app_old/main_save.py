import sys
import os
import argparse
from datetime import datetime
from app.input_handler import get_user_input, process_and_store_input
from app.database import SessionLocal, create_entry
from app.retrieval import get_entries_by_date, get_entries_by_category, search_entries, format_entries

# Add the root directory to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def validate_date(date_str):
    # Validate date format
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        print("Invalid date format. Use 'YYYY-MM-DD'.")
        return False


def validate_date_range(date_str):
    dates = date_str.split(",")
    if len(dates) == 2:
        start_date = validate_date(dates[0])
        end_date = validate_date(dates[1])
        if start_date and end_date:
            return start_date, end_date
    print("Invalid date range. Use 'YYYY-MM-DD,YYYY-MM-DD'.")
    return None, None


def validate_categories(categories_str):
    # Validate categories format
    categories = categories_str.split(",")
    if all(category.strip() for category in categories):
        return categories
    print("Invalid categories format. Use comma-separated values.")
    return None


def validate_keyword(keyword_str):
    # Validate keyword format
    if keyword_str.strip():
        return keyword_str.strip()
    print("Invalid keyword format. Please enter a keyword.")
    return None


def display_entries(entries):
    # Display entries
    for entry in entries:
        print(entry)


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Journal Bot")
    parser.add_argument(
        "--entry",
        "-e",
        help="Add a new journal entry"
    )
    parser.add_argument(
        "--categories",
        "-c",
        help="Add categories to the journal entry"
    )
    parser.add_argument(
        "--view-date",
        "-vd",
        help="View journal entries by date or range (e.g., 'YYYY-MM-DD' or 'YYYY-MM-DD,YYYY-MM-DD')."
    )
    parser.add_argument(
        "--view-category",
        "-vc",
        help="View journal entries by category."
    )
    parser.add_argument(
        "--search",
        "-s",
        help="Search journal entries by keyword."
    )
    args = parser.parse_args()

    # Validate and process command-line arguments
    if args.entry:
        input_data = get_user_input()
        process_and_store_input(input_data, args.categories)
    elif args.view_date:
        start_date, end_date = validate_date_range(args.view_date)
        if start_date and end_date:
            entries = get_entries_by_date(start_date, end_date)
            display_entries(entries)
    elif args.view_category:
        categories = validate_categories(args.view_category)
        if categories:
            entries = get_entries_by_category(categories)
            display_entries(entries)
    elif args.search:
        keyword = validate_keyword(args.search)
        if keyword:
            entries = search_entries(keyword)
            display_entries(entries)
    else:
        # Interactive mode
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
                entries = get_entries_by_category(view_category)
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


if __name__ == "__main__":
    main()
