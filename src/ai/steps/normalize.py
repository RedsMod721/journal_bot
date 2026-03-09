"""Step 03 — Normalise raw entry text to a canonical form.

Collapses all interior whitespace (tabs, newlines, multiple spaces) to a
single space so that downstream word-count, keyword, and embedding steps
operate on a stable, deterministic string.
"""

from __future__ import annotations

from typing import Any


def run(content: str) -> dict[str, Any]:
    """Normalise *content* and return basic text metrics.

    Args:
        content: Raw journal entry text (may be empty or None-like).

    Returns:
        Dict with keys:
            ``canonical_text`` — whitespace-normalised string.
            ``char_count``     — character count of canonical text.
            ``word_count``     — word count of canonical text.
    """
    canonical = " ".join((content or "").strip().split())
    return {
        "canonical_text": canonical,
        "char_count": len(canonical),
        "word_count": len(canonical.split()),
    }
