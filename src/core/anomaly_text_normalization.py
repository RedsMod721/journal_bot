"""Anomaly detection text normalization.

Implements Section 9.2 (Text Normalization) from COMPLETE_ARCHITECTURE.md.

CRITICAL — normalization must be deterministic: same input → same output.
Steps are applied in fixed order; do NOT reorder them.
"""

from __future__ import annotations

import unicodedata
from typing import List

# ── Caps (Section 9.0.6) ────────────────────────────────────────────────────
MAX_NORM_CHARS: int = 10_000
MAX_TOKENS: int = 2_000

# ── Canonical stopword set (Section 9.2.3, version stopwords_enfr_v1) ───────
#    Used ONLY for similarity shingles — NOT for marker detection.
STOPWORDS_ENFR_V1: frozenset[str] = frozenset(
    {
        # English
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "he",
        "her",
        "hers",
        "him",
        "his",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "ours",
        "she",
        "so",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "too",
        "us",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "you",
        "your",
        "yours",
        # French
        "ai",
        "aie",
        "aient",
        "ait",
        "au",
        "aux",
        "avec",
        "ce",
        "ces",
        "cet",
        "cette",
        "dans",
        "de",
        "des",
        "du",
        "elle",
        "elles",
        "en",
        "est",
        "et",
        "eux",
        "il",
        "ils",
        "je",
        "la",
        "le",
        "les",
        "leur",
        "leurs",
        "lui",
        "ma",
        "mais",
        "me",
        "mes",
        "moi",
        "mon",
        "ne",
        "nos",
        "notre",
        "nous",
        "on",
        "ou",
        "par",
        "pas",
        "pour",
        "qu",
        "que",
        "qui",
        "sa",
        "se",
        "ses",
        "son",
        "sur",
        "ta",
        "te",
        "tes",
        "toi",
        "ton",
        "tu",
        "un",
        "une",
        "vos",
        "votre",
        "vous",
    }
)

# Minimum token count for meaningful similarity comparison (Section 9.2.2)
_MIN_TOKENS_FOR_SIMILARITY: int = 10


class TextNormalizer:
    """Normalize text for anomaly detection signal extraction.

    All methods are stateless and suitable for use at module level via
    ``TextNormalizer.<method>()``.
    """

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize raw text for downstream tokenization (Section 9.2.1).

        Steps (fixed order — do NOT reorder):
          1. Truncate to MAX_NORM_CHARS before any processing
          2. NFKC Unicode normalization
          3. Casefold (more aggressive than lower(); handles ß, etc.)
          4. Replace any character that is not a Unicode letter or digit with a space
          5. Collapse consecutive whitespace; strip leading/trailing space

        Returns the empty string when ``text`` is falsy.
        """
        if not text:
            return ""

        # 1. Truncate
        text = text[:MAX_NORM_CHARS]

        # 2. NFKC normalization — compatibility decomposition → composition
        text = unicodedata.normalize("NFKC", text)

        # 3. Casefold
        text = text.casefold()

        # 4. Keep only Unicode letters (L*) and digits (N*)
        buf: List[str] = []
        for ch in text:
            cat = unicodedata.category(ch)
            if cat[0] in ("L", "N"):
                buf.append(ch)
            else:
                buf.append(" ")

        # 5. Collapse whitespace + trim
        return " ".join("".join(buf).split())

    @staticmethod
    def tokenize(normalized_text: str) -> List[str]:
        """Tokenize a normalized string (Section 9.2.2).

        Rules:
          - Split on whitespace
          - Drop tokens shorter than 2 characters
          - Hard cap at MAX_TOKENS (keeps earliest tokens)
        """
        if not normalized_text:
            return []

        tokens = [t for t in normalized_text.split() if len(t) >= 2]
        return tokens[:MAX_TOKENS]

    @staticmethod
    def remove_stopwords(tokens: List[str]) -> List[str]:
        """Remove stopwords_enfr_v1 from a token list.

        CRITICAL (Section 9.2.3):
          - Use ONLY for similarity shingles (tokens_sim).
          - Do NOT apply to marker detection tokens (tokens_all).
        """
        return [t for t in tokens if t not in STOPWORDS_ENFR_V1]

    @staticmethod
    def normalize_and_tokenize(
        text: str,
    ) -> tuple[List[str], List[str], int]:
        """Full normalization pipeline: normalize → tokenize → split streams.

        Returns:
            tokens_all  — all tokens after normalization; used for marker detection.
            tokens_sim  — tokens_all minus stopwords; used for similarity shingles.
                          Empty list when token_count < _MIN_TOKENS_FOR_SIMILARITY
                          (insufficient signal per Section 9.2.2).
            token_count — len(tokens_all) before stopword removal.
        """
        normalized = TextNormalizer.normalize_text(text)
        tokens_all = TextNormalizer.tokenize(normalized)
        token_count = len(tokens_all)

        if token_count < _MIN_TOKENS_FOR_SIMILARITY:
            # Insufficient signal — skip similarity stream
            return tokens_all, [], token_count

        tokens_sim = TextNormalizer.remove_stopwords(tokens_all)
        return tokens_all, tokens_sim, token_count
