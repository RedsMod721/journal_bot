from app.input_handler import process_and_store_input
from app.retrieval import get_entries_by_date, get_entries_by_category, search_entries
from app.display import display_entries
from app.validators import validate_date_range, validate_categories, validate_keyword

def handle_command_line_args(args):
    if args.entry:
        process_and_store_input(args.entry, args.categories)
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
