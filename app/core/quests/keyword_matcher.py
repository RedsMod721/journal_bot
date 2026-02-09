"""
Keyword matching with NLTK stemming and fuzzy typo tolerance.

This module provides intelligent keyword matching that handles:
- Morphological variations (run -> running, walked -> walk)
- Common typos (excercise -> exercise)
- Case insensitivity

Uses Porter stemming from NLTK and SequenceMatcher for fuzzy matching.
"""

from difflib import SequenceMatcher

from nltk.stem import PorterStemmer
from nltk.tokenize import word_tokenize


class KeywordMatcher:
    """
    Matches keywords in text using stemming and fuzzy matching.

    Combines two strategies for robust keyword detection:
    1. Stem matching: Handles morphological variations (run/running/ran)
    2. Fuzzy matching: Handles typos with configurable similarity threshold

    Example:
        matcher = KeywordMatcher()
        text = "Went running at the gym. Great excercise!"
        keywords = ["run", "exercise", "gym"]

        matched = matcher.match_keywords(text, keywords)
        # Returns: ["run", "gym", "exercise"]
        # - "run" matches "running" (stem match)
        # - "gym" matches "gym" (exact match)
        # - "exercise" matches "excercise" (fuzzy match)
    """

    def __init__(self, typo_threshold: float = 0.85) -> None:
        """
        Initialize the keyword matcher.

        Args:
            typo_threshold: Minimum similarity ratio for fuzzy matching (0.0-1.0).
                           Default 0.85 (85% similarity required).
        """
        self._stemmer = PorterStemmer()
        self.typo_threshold = typo_threshold

    def match_keywords(self, text: str, keywords: list[str]) -> list[str]:
        """
        Find all keywords that match in the given text.

        Args:
            text: The text to search for keywords
            keywords: List of keywords to look for

        Returns:
            List of matched keywords (from the input list, not the text)
        """
        if not text or not keywords:
            return []

        text_tokens = self._tokenize_and_stem(text)
        text_tokens_lower = [token.lower() for token in word_tokenize(text.lower())]

        matched: list[str] = []
        seen: set[str] = set()

        for keyword in keywords:
            keyword_key = keyword.lower()
            if keyword_key in seen:
                continue
            if self._keyword_matches(keyword, text_tokens, text_tokens_lower):
                matched.append(keyword)
                seen.add(keyword_key)

        return matched

    def _tokenize_and_stem(self, text: str) -> list[str]:
        """
        Tokenize text and stem each token.

        Args:
            text: The text to process

        Returns:
            List of stemmed tokens
        """
        tokens = word_tokenize(text.lower())
        return [self._stemmer.stem(token) for token in tokens]

    def _keyword_matches(
        self,
        keyword: str,
        stemmed_tokens: list[str],
        original_tokens: list[str],
    ) -> bool:
        """
        Check if a keyword matches any token in the text.

        Args:
            keyword: The keyword to look for
            stemmed_tokens: Stemmed tokens from the text
            original_tokens: Original lowercase tokens from the text

        Returns:
            True if keyword matches via stem or fuzzy matching
        """
        keyword_lower = keyword.lower()
        keyword_stem = self._stemmer.stem(keyword_lower)

        if keyword_stem in stemmed_tokens:
            return True

        for token in original_tokens:
            if self._fuzzy_match(keyword_lower, token):
                return True

        return False

    def _fuzzy_match(self, keyword: str, token: str) -> bool:
        """
        Check if keyword and token are similar enough (typo tolerance).

        Uses SequenceMatcher to calculate string similarity ratio.

        Args:
            keyword: The keyword to match
            token: The token from text to compare

        Returns:
            True if similarity ratio >= typo_threshold
        """
        if len(keyword) < 4 or len(token) < 4:
            return keyword == token

        similarity = SequenceMatcher(None, keyword, token).ratio()
        return similarity >= self.typo_threshold
