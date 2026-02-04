from datetime import datetime

def validate_date(date_str):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
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
            return dates[0], dates[1]
    print("Invalid date range. Use 'YYYY-MM-DD,YYYY-MM-DD'.")
    return None, None

def validate_categories(categories_str):
    categories = categories_str.split(",")
    if all(category.strip() for category in categories):
        return categories
    print("Invalid categories format. Use comma-separated values.")
    return None

def validate_keyword(keyword_str):
    if keyword_str.strip():
        return keyword_str.strip()
    print("Invalid keyword format. Please enter a keyword.")
    return None
