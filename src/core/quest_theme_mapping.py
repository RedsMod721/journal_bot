"""
Theme XP mapping loader.

Implements Section 10.7 (Theme XP Derivation Q22 EXTRA) from architecture.

Supported artifact shapes:
    Legacy runtime format:
        {
            "schema_version": 1,
            "mappings": {
                "<skill_key>": [
                    {"theme_name": "<canonical_theme_name>", "theme_weight_bp": <int>},
                    ...
                ]
            }
        }

    Canonical seed artifact format:
        {
            "schema_version": 1,
            "mappings": [
                {
                    "skill_semantic_key": "<skill_key>",
                    "themes": [
                        {
                            "theme_semantic_key": "theme_professional",
                            "theme_weight_bp": 7000
                        }
                    ]
                }
            ]
        }

Section 10.7.2:
    File is pinned at startup; sha256(file_bytes) is logged for replay audit.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List

from src.core.themes import CANONICAL_THEME_NAMES, canonicalize_theme_name

logger = logging.getLogger(__name__)

_VALID_THEME_NAMES: frozenset[str] = frozenset(CANONICAL_THEME_NAMES)


class ThemeMapping:
    """
    Versioned theme XP mapping configuration.

    Loaded once at startup from a JSON artifact; sha256 is logged for audit.
    Thread-safe for concurrent reads (immutable after __init__).
    """

    def __init__(self, mapping_file_path: str) -> None:
        self.mapping_file_path = Path(mapping_file_path)
        self.schema_version: int | None = None
        # {normalized_skill_key: [{theme_name, theme_weight_bp}, ...]}
        self.mappings: Dict[str, List[Dict]] = {}
        self.file_hash: str | None = None

        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """
        Load and validate the mapping file (Section 10.7.2).

        Logs the sha256 hash so replay runs can confirm they used the same
        mapping artifact.
        """
        if not self.mapping_file_path.exists():
            raise FileNotFoundError(
                f"Theme mapping file not found: {self.mapping_file_path}"
            )

        file_bytes = self.mapping_file_path.read_bytes()

        # Section 10.7.2: pin at startup, log hash
        self.file_hash = hashlib.sha256(file_bytes).hexdigest()
        logger.info(
            "theme_mapping loaded path=%s sha256=%s",
            self.mapping_file_path,
            self.file_hash,
        )

        data = json.loads(file_bytes.decode("utf-8"))

        if "schema_version" not in data:
            raise ValueError("Theme mapping missing schema_version")
        if data["schema_version"] != 1:
            raise ValueError(f"Unsupported schema_version: {data['schema_version']}")
        if "mappings" not in data:
            raise ValueError("Theme mapping missing mappings")

        self.schema_version = data["schema_version"]
        self.mappings = self._normalize_mappings(data["mappings"])

        self._validate_mappings()

    def _normalize_mappings(self, raw_mappings: object) -> Dict[str, List[Dict]]:
        """Normalize legacy and canonical artifact shapes to one lookup map."""
        if isinstance(raw_mappings, dict):
            return {
                self._normalize_skill_key(skill_key): list(entries)
                for skill_key, entries in raw_mappings.items()
            }

        if not isinstance(raw_mappings, list):
            raise ValueError("Theme mapping 'mappings' must be a dict or list")

        normalized: Dict[str, List[Dict]] = {}
        for idx, row in enumerate(raw_mappings, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"Theme mapping row {idx} must be an object")

            skill_key = self._normalize_skill_key(row.get("skill_semantic_key"))
            if not skill_key:
                raise ValueError(
                    f"Theme mapping row {idx} missing skill_semantic_key"
                )

            themes = row.get("themes", [])
            if not isinstance(themes, list):
                raise ValueError(
                    f"Theme mapping row {idx} themes must be a list"
                )

            normalized[skill_key] = [
                {
                    "theme_name": self._normalize_theme_name(
                        entry.get("theme_name")
                        or entry.get("theme_semantic_key")
                    ),
                    "theme_weight_bp": entry.get("theme_weight_bp"),
                }
                for entry in themes
            ]

        return normalized

    def _normalize_skill_key(self, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip().lower().replace(" ", "_")

    def _normalize_theme_name(self, value: object) -> str:
        if value is None:
            return ""
        raw = str(value).strip()
        canonical = canonicalize_theme_name(raw)
        if canonical is not None:
            return canonical
        if raw.lower().startswith("theme_"):
            candidate = raw[6:].replace("_", " ").title()
            canonical = canonicalize_theme_name(candidate)
            if canonical is not None:
                return canonical
        return raw

    def _validate_mappings(self) -> None:
        """Validate structure and theme name correctness."""
        for skill_key, themes in self.mappings.items():
            if not isinstance(themes, list):
                raise ValueError(
                    f"Mapping for skill '{skill_key}' must be a list"
                )

            total_weight = 0
            for entry in themes:
                if "theme_name" not in entry:
                    raise ValueError(
                        f"Entry in mapping for '{skill_key}' missing 'theme_name'"
                    )
                if "theme_weight_bp" not in entry:
                    raise ValueError(
                        f"Entry in mapping for '{skill_key}' missing 'theme_weight_bp'"
                    )

                theme_name = entry["theme_name"]
                if theme_name not in _VALID_THEME_NAMES:
                    raise ValueError(
                        f"Unknown theme name '{theme_name}' in mapping for '{skill_key}'. "
                        f"Valid names: {sorted(_VALID_THEME_NAMES)}"
                    )

                weight = entry["theme_weight_bp"]
                if not isinstance(weight, int) or weight <= 0:
                    raise ValueError(
                        f"theme_weight_bp for '{theme_name}' in '{skill_key}' "
                        f"must be a positive integer, got {weight!r}"
                    )
                total_weight += weight

            if total_weight <= 0:
                raise ValueError(
                    f"Total theme_weight_bp for skill '{skill_key}' must be > 0"
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_themes_for_skill(self, *skill_keys: str | None) -> List[Dict]:
        """
        Return theme entries for the first matching skill key.

        Returns:
            [{theme_name: str, theme_weight_bp: int}, ...]
            Empty list when the skill has no theme mappings.
        """
        for key in skill_keys:
            normalized = self._normalize_skill_key(key)
            if normalized and normalized in self.mappings:
                return self.mappings[normalized]
        return []

    def candidate_keys_for_skill(
        self,
        *,
        canonical_name: str | None,
        source_skill_id: str | None,
    ) -> list[str]:
        """Return deterministic lookup candidates for a skill."""
        candidates: list[str] = []
        for raw in (
            source_skill_id,
            canonical_name,
            f"skill_{canonical_name}" if canonical_name else None,
        ):
            normalized = self._normalize_skill_key(raw)
            if normalized and normalized not in candidates:
                candidates.append(normalized)
        return candidates

    def get_file_hash(self) -> str:
        """Return the sha256 hex digest of the mapping file."""
        assert self.file_hash is not None  # guaranteed by _load
        return self.file_hash
