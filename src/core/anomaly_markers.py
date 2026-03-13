"""
Anomaly detection marker matching.

Implements Section 9.4 (Marker Matching Rules) from architecture.
"""
from __future__ import annotations

from typing import List, Set, Tuple


# ── Canonical marker sets (Section 9.4.1, version anomaly_markers_v1) ────────

FARMING_TOKENS: Set[str] = {"xp", "farm", "farming", "exploit", "macro"}
FARMING_PHRASES: List[Tuple[str, ...]] = [
    ("grind", "for", "xp"),
    ("farm", "for", "xp"),
]

CREATIVITY_TOKENS: Set[str] = {
    "creative", "invented", "novel", "unexpected", "weird", "clever",
    "hack", "hacked", "prototype", "experiment", "solution", "trick",
    "idea", "improvised", "repurposed", "reinvented", "custom",
}
CREATIVITY_PHRASES: List[Tuple[str, ...]] = [
    ("new", "approach"),
    ("fun", "idea"),
    ("came", "up", "with"),
    ("figured", "out", "a", "solution"),
    ("different", "way"),
]

AUTOMATION_TOKENS: Set[str] = {
    "script", "automate", "automation", "pipeline", "tool", "build",
    "coded", "programmed", "bot",
}
AUTOMATION_PHRASES: List[Tuple[str, ...]] = [
    ("wrote", "a", "script"),
    ("built", "a", "tool"),
]

CONSTRAINT_TOKENS: Set[str] = {
    "optimize", "optimized", "optimization", "shortcut", "constraint",
    "workaround", "workflow", "template", "system", "streamlined",
}
CONSTRAINT_PHRASES: List[Tuple[str, ...]] = [
    ("work", "around", "it"),
    ("set", "up", "a", "workflow"),
]

COMBO_CONNECTOR_TOKENS: Set[str] = {
    "combined", "while", "during", "simultaneously", "alongside", "plus",
}
COMBO_CONNECTOR_PHRASES: List[Tuple[str, ...]] = [
    ("at", "the", "same", "time"),
]


class MarkerDetector:
    """Detect anomaly markers in text."""

    # ------------------------------------------------------------------
    # Primitives
    # ------------------------------------------------------------------

    @staticmethod
    def match_tokens(tokens: List[str], marker_set: Set[str]) -> int:
        """Count unique token matches.

        Section 9.4.1: Each marker contributes at most 1 hit per entry.
        """
        return len(set(tokens) & marker_set)

    @staticmethod
    def match_phrases(tokens: List[str], phrase_list: List[Tuple[str, ...]]) -> int:
        """Count unique phrase matches.

        Section 9.4.1: Each marker contributes at most 1 hit per entry.
        """
        if not tokens:
            return 0

        matched: Set[Tuple[str, ...]] = set()
        for phrase in phrase_list:
            phrase_len = len(phrase)
            for i in range(len(tokens) - phrase_len + 1):
                if tuple(tokens[i : i + phrase_len]) == phrase:
                    matched.add(phrase)
                    break  # each phrase counts only once

        return len(matched)

    # ------------------------------------------------------------------
    # Per-category detectors
    # ------------------------------------------------------------------

    @staticmethod
    def detect_farming(tokens_all: List[str]) -> int:
        """Detect farming markers (token hits + phrase hits)."""
        return MarkerDetector.match_tokens(tokens_all, FARMING_TOKENS) + \
               MarkerDetector.match_phrases(tokens_all, FARMING_PHRASES)

    @staticmethod
    def detect_creativity(tokens_all: List[str]) -> int:
        """Detect creativity markers."""
        return MarkerDetector.match_tokens(tokens_all, CREATIVITY_TOKENS) + \
               MarkerDetector.match_phrases(tokens_all, CREATIVITY_PHRASES)

    @staticmethod
    def detect_automation(tokens_all: List[str], has_farming: bool) -> int:
        """Detect automation markers.

        Section 9.4.2: If farming detected, exclude "macro" from automation
        tokens to prevent double-counting.
        """
        automation_tokens = AUTOMATION_TOKENS - {"macro"} if has_farming else AUTOMATION_TOKENS
        return MarkerDetector.match_tokens(tokens_all, automation_tokens) + \
               MarkerDetector.match_phrases(tokens_all, AUTOMATION_PHRASES)

    @staticmethod
    def detect_constraint(tokens_all: List[str]) -> int:
        """Detect constraint/optimization markers."""
        return MarkerDetector.match_tokens(tokens_all, CONSTRAINT_TOKENS) + \
               MarkerDetector.match_phrases(tokens_all, CONSTRAINT_PHRASES)

    @staticmethod
    def detect_combo_connectors(tokens_all: List[str]) -> int:
        """Detect combo connector markers."""
        return MarkerDetector.match_tokens(tokens_all, COMBO_CONNECTOR_TOKENS) + \
               MarkerDetector.match_phrases(tokens_all, COMBO_CONNECTOR_PHRASES)
