def display_entries(entries):
    for entry in entries:
        print(f"ID: {entry.id}, Timestamp: {entry.timestamp}, Content: {entry.content}, Categories: {entry.categories}")
