"""Tests for keyword matcher."""

import pytest

from app.core.quests.keyword_matcher import KeywordMatcher


def test_keyword_matcher_exact_match() -> None:
    matcher = KeywordMatcher()
    text = "Went to the gym."
    keywords = ["gym"]

    assert matcher.match_keywords(text, keywords) == ["gym"]


def test_keyword_matcher_stem_match() -> None:
    matcher = KeywordMatcher()
    text = "Went running today."
    keywords = ["run"]

    assert matcher.match_keywords(text, keywords) == ["run"]


def test_keyword_matcher_fuzzy_match_typo() -> None:
    matcher = KeywordMatcher()
    text = "Great excercise!"
    keywords = ["exercise"]

    assert matcher.match_keywords(text, keywords) == ["exercise"]


def test_keyword_matcher_case_insensitive() -> None:
    matcher = KeywordMatcher()
    text = "RUNNING at the GYM."
    keywords = ["run", "gym"]

    assert matcher.match_keywords(text, keywords) == ["run", "gym"]


def test_keyword_matcher_multiple_keywords() -> None:
    matcher = KeywordMatcher()
    text = "Went running at the gym. Great excercise!"
    keywords = ["run", "gym", "exercise"]

    assert matcher.match_keywords(text, keywords) == ["run", "gym", "exercise"]


def test_keyword_matcher_no_matches_returns_empty() -> None:
    matcher = KeywordMatcher()
    text = "Stayed home and rested."
    keywords = ["run", "exercise"]

    assert matcher.match_keywords(text, keywords) == []


def test_keyword_matcher_duplicate_matches_returned_once() -> None:
    matcher = KeywordMatcher()
    text = "Went running."
    keywords = ["run", "run"]

    assert matcher.match_keywords(text, keywords) == ["run"]


def test_keyword_matcher_short_words_require_exact_match() -> None:
    matcher = KeywordMatcher()
    text = "Into the item store."
    keywords = ["in", "it"]

    assert matcher.match_keywords(text, keywords) == []


def test_keyword_matcher_punctuation_handling() -> None:
    matcher = KeywordMatcher()
    text = "Gym, run!"
    keywords = ["gym", "run"]

    assert matcher.match_keywords(text, keywords) == ["gym", "run"]


def test_keyword_matcher_threshold_boundary() -> None:
    matcher = KeywordMatcher()

    keyword_fail = "a" * 25
    token_fail = "a" * 21 + "b" * 4

    assert matcher.match_keywords(token_fail, [keyword_fail]) == []

    keyword_pass = "a" * 20
    token_pass = "a" * 17 + "b" * 3

    assert matcher.match_keywords(token_pass, [keyword_pass]) == [keyword_pass]


def test_keyword_matcher_empty_text_returns_empty() -> None:
    matcher = KeywordMatcher()
    assert matcher.match_keywords("", ["run"]) == []


def test_keyword_matcher_empty_keywords_returns_empty() -> None:
    matcher = KeywordMatcher()
    assert matcher.match_keywords("run", []) == []


def test_keyword_matcher_none_text_or_keywords() -> None:
    matcher = KeywordMatcher()
    assert matcher.match_keywords(None, ["run"]) == []
    assert matcher.match_keywords("run", None) == []


def test_keyword_matcher_preserves_input_order() -> None:
    matcher = KeywordMatcher()
    text = "run gym"
    keywords = ["gym", "run"]

    assert matcher.match_keywords(text, keywords) == ["gym", "run"]


def test_keyword_matcher_duplicate_keywords_case_insensitive_dedup() -> None:
    matcher = KeywordMatcher()
    text = "running"
    keywords = ["Run", "run"]

    assert matcher.match_keywords(text, keywords) == ["Run"]


def test_keyword_matcher_multiple_occurrences_single_keyword_once() -> None:
    matcher = KeywordMatcher()
    text = "run run run"
    keywords = ["run"]

    assert matcher.match_keywords(text, keywords) == ["run"]


def test_keyword_matcher_stem_match_past_tense() -> None:
    matcher = KeywordMatcher()
    text = "She walked home."
    keywords = ["walk"]

    assert matcher.match_keywords(text, keywords) == ["walk"]


def test_keyword_matcher_stem_match_irregular() -> None:
    matcher = KeywordMatcher()
    text = "He ran fast."
    keywords = ["run"]

    assert matcher.match_keywords(text, keywords) == []


def test_keyword_matcher_fuzzy_match_case_insensitive() -> None:
    matcher = KeywordMatcher()
    text = "Great EXCERCISE today!"
    keywords = ["exercise"]

    assert matcher.match_keywords(text, keywords) == ["exercise"]


def test_keyword_matcher_fuzzy_match_short_token_disabled() -> None:
    matcher = KeywordMatcher()
    text = "runn"
    keywords = ["run"]

    assert matcher.match_keywords(text, keywords) == []


def test_keyword_matcher_numeric_tokens_matched() -> None:
    matcher = KeywordMatcher()
    text = "Completed 10 reps."
    keywords = ["10"]

    assert matcher.match_keywords(text, keywords) == ["10"]


def test_keyword_matcher_hyphenated_words() -> None:
    matcher = KeywordMatcher()
    text = "Focus on well-being daily."
    keywords = ["well-being"]

    assert matcher.match_keywords(text, keywords) == ["well-being"]


def test_keyword_matcher_apostrophes() -> None:
    matcher = KeywordMatcher()
    text = "I don't agree."
    keywords = ["dont"]

    assert matcher.match_keywords(text, keywords) == []


def test_keyword_matcher_unicode_accents() -> None:
    matcher = KeywordMatcher()
    text = "Met at the café."
    keywords = ["café"]

    assert matcher.match_keywords(text, keywords) == ["café"]


def test_keyword_matcher_non_english_text() -> None:
    matcher = KeywordMatcher()
    text = "Mañana será otro día."
    keywords = ["mañana"]

    assert matcher.match_keywords(text, keywords) == ["mañana"]


def test_keyword_matcher_whitespace_only_text() -> None:
    matcher = KeywordMatcher()
    assert matcher.match_keywords("   ", ["run"]) == []


def test_keyword_matcher_keyword_with_punctuation() -> None:
    matcher = KeywordMatcher()
    text = "gym"
    keywords = ["gym!"]

    assert matcher.match_keywords(text, keywords) == []


def test_keyword_matcher_large_input_performance_smoke() -> None:
    matcher = KeywordMatcher()
    words = [f"word{i}" for i in range(100)]
    text = " ".join(words)
    keywords = ["word1", "word50", "word99"]

    assert matcher.match_keywords(text, keywords) == ["word1", "word50", "word99"]


def test_keyword_matcher_threshold_custom_override() -> None:
    matcher = KeywordMatcher(typo_threshold=0.9)
    keyword = "a" * 20
    token = "a" * 17 + "b" * 3

    assert matcher.match_keywords(token, [keyword]) == []


def test_keyword_matcher_fuzzy_match_token_substitution() -> None:
    matcher = KeywordMatcher()
    keyword = "abcdefghij"
    text = "abcdxfghij"

    assert matcher.match_keywords(text, [keyword]) == [keyword]


def test_keyword_matcher_fuzzy_match_transposition() -> None:
    matcher = KeywordMatcher()
    keyword = "abcdefghij"
    text = "abcedfghij"

    assert matcher.match_keywords(text, [keyword]) == [keyword]


def test_keyword_matcher_fuzzy_match_insertion_deletion() -> None:
    matcher = KeywordMatcher()
    keyword = "abcdefghij"
    text = "abcdefghi"

    assert matcher.match_keywords(text, [keyword]) == [keyword]


def test_keyword_matcher_stem_and_fuzzy_both_match_no_dup() -> None:
    matcher = KeywordMatcher()
    text = "running runnng"
    keywords = ["run"]

    assert matcher.match_keywords(text, keywords) == ["run"]
