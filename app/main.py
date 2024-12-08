import sys
import os

# Add the root directory to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.input_handler import get_user_input, process_and_store_input

def main():
    print("=== Journal Entry Test Run ===")
    
    # Step 1: Get user input
    content = get_user_input()
    
    # Step 2: Validate and store the input
    if content:
        process_and_store_input(content, categories="test,example")
    else:
        print("No entry was saved.")

if __name__ == "__main__":
    main()