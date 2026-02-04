import sys
import os
import argparse
from app.cli_handler import handle_command_line_args
from app.interactive import interactive_mode

# Add the root directory to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Journal Bot")
    parser.add_argument("--entry", "-e", help="Add a new journal entry")
    parser.add_argument("--categories", "-c", help="Add categories to the journal entry")
    parser.add_argument("--view-date", "-vd", help="View journal entries by date or range.")
    parser.add_argument("--view-category", "-vc", help="View journal entries by category.")
    parser.add_argument("--search", "-s", help="Search journal entries by keyword.")
    args = parser.parse_args()

    if any([args.entry, args.view_date, args.view_category, args.search]):
        handle_command_line_args(args)
    else:
        interactive_mode()

if __name__ == "__main__":
    main()
