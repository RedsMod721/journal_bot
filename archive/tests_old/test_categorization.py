from app.categorization import extract_keywords  # Assuming extract_keywords is defined in app/categorization.py

def test_extract_keywords_simple_content():
    entry_content = "I am happy and went for a run"
    expected_output = ["happy", "run"]  # Expect "went" to be excluded
    assert extract_keywords(entry_content) == expected_output

def test_extract_keywords_complex_content():
    entry_content = "The idea of exercising daily is great for mental health."
    expected_output = ["idea", "exercise", "daily", "great", "mental", "health"]
    assert extract_keywords(entry_content) == expected_output

def test_extract_keywords_content_with_special_characters():
    entry_content = "Tasks: Complete project! Review code @work."
    expected_output = ["task", "complete", "project", "review", "code", "work"]
    assert extract_keywords(entry_content) == expected_output

def test_extract_keywords_content_with_mixed_case():
    entry_content = "Feeling SAD about missed deadlines."
    expected_output = ["feel", "sad", "miss", "deadline"]
    assert extract_keywords(entry_content) == expected_output

def test_extract_keywords_empty_content():
    entry_content = ""
    expected_output = []
    assert extract_keywords(entry_content) == expected_output

def test_extract_keywords_content_with_only_stop_words():
    entry_content = "the and or but"
    expected_output = []
    assert extract_keywords(entry_content) == expected_output

def test_extract_keywords_content_with_only_special_characters():
    entry_content = "!!! @@@ ### $$$"
    expected_output = []
    assert extract_keywords(entry_content) == expected_output