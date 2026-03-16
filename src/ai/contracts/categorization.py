"""
Categorization contract (v1) — Section 11.3.1.

Output schema:
{
  "contract_version": 1,
  "skill_id": "33333333333333333333333333333333",   // nullable
  "theme_ids": ["11111111111111111111111111111111"],
  "tags": ["focus", "work"],
  "signals": { "energy": 76, "valence": 58, "success": 70 },
  "citations": []
}

Persistence mapping (Section 11.3.1, schema-aligned):
  signals.energy  -> journal_entries_structured.energy_level
                     ROUND_HALF_UP(energy / 10.0), clamp 1..10
  signals.success -> journal_entries_structured.success_quality
                     ROUND_HALF_UP(success / 10.0), clamp 0..10
  signals.valence -> journal_entries_structured.sentiment_score
                     (valence - 50) / 50, rounded 3dp, clamp [-1.0, 1.0]
  tags[]          -> journal_entries_structured.categories (normalized array)
  skill_id + theme_ids -> journal_entries_structured.skills_themes_involved
"""

from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Literal, Optional

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.ai.contracts import BaseAIContract, CitationItem, ContractRegistry

_HEX32_RE = re.compile(r"^[0-9a-f]{32}$")


def _is_valid_id(v: str) -> bool:
    return bool(_HEX32_RE.match(v))


# --------------------------------------------------------------------------- #
# Signals nested object                                                         #
# --------------------------------------------------------------------------- #


class CategorizationSignals(BaseModel):
    """
    Signals sub-object (Section 11.3.1).

    Exactly three integer keys: energy, valence, success — all 0..100.
    Unknown keys rejected.
    """

    model_config = ConfigDict(extra="forbid")

    energy: int = Field(..., ge=0, le=100)
    valence: int = Field(..., ge=0, le=100)
    success: int = Field(..., ge=0, le=100)


# --------------------------------------------------------------------------- #
# Categorization contract                                                       #
# --------------------------------------------------------------------------- #


class CategorizationContract(BaseAIContract):
    """
    Categorization contract (v1) — Section 11.3.1.

    Required keys: contract_version, skill_id, theme_ids, tags, signals, citations.
    Unknown keys rejected (inherited extra='forbid').
    """

    contract_version: Literal[1] = 1

    skill_id: Optional[str] = None
    theme_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    signals: CategorizationSignals
    citations: List[CitationItem] = Field(default_factory=list)

    # ---------------------------------------------------------------------- #
    # Field validators                                                          #
    # ---------------------------------------------------------------------- #

    @field_validator("skill_id")
    @classmethod
    def _validate_skill_id(cls, v: Optional[str]) -> Optional[str]:
        """skill_id: nullable; if non-null must be 32-hex (Section 11.3.1)."""
        if v is not None and not _is_valid_id(v):
            raise ValueError(
                f"skill_id must be 32-hex lowercase or null, got: {v!r}"
            )
        return v

    @field_validator("theme_ids")
    @classmethod
    def _validate_theme_ids(cls, v: List[str]) -> List[str]:
        """theme_ids: max 8, each 32-hex, duplicates rejected (Section 11.3.1)."""
        if len(v) > 8:
            raise ValueError(f"theme_ids max 8 items, got {len(v)}")
        seen: set[str] = set()
        for tid in v:
            if not _is_valid_id(tid):
                raise ValueError(
                    f"Each theme_id must be 32-hex lowercase, got: {tid!r}"
                )
            if tid in seen:
                raise ValueError(f"Duplicate theme_id rejected: {tid!r}")
            seen.add(tid)
        return v

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: List[str]) -> List[str]:
        """
        tags: max 12; each 1..32 code points after NFC normalization.

        Duplicates rejected after lowercase+trim normalization (Section 11.3.1).
        Persisted values ARE the normalized strings.
        """
        if len(v) > 12:
            raise ValueError(f"tags max 12 items, got {len(v)}")

        normalized: list[str] = []
        seen: set[str] = set()

        for raw_tag in v:
            tag = unicodedata.normalize("NFC", raw_tag).strip()
            tag = " ".join(tag.split())   # collapse internal whitespace
            tag_lower = tag.lower()

            if len(tag_lower) < 1 or len(tag_lower) > 32:
                raise ValueError(
                    f"Each tag must be 1..32 code points after normalization, "
                    f"got {len(tag_lower)}: {raw_tag!r}"
                )
            if tag_lower in seen:
                raise ValueError(
                    f"Duplicate tag rejected (after normalization): {raw_tag!r}"
                )
            seen.add(tag_lower)
            normalized.append(tag_lower)  # persist normalized form

        return normalized

    @model_validator(mode="after")
    def _log_contract_loaded(self) -> "CategorizationContract":
        logger.debug(
            "[ai_contract][categorization] loaded skill_id={} "
            "theme_ids_count={} tags_count={} energy={} valence={} success={}",
            self.skill_id,
            len(self.theme_ids),
            len(self.tags),
            self.signals.energy,
            self.signals.valence,
            self.signals.success,
        )
        return self

    # ---------------------------------------------------------------------- #
    # Persistence helpers (Section 11.3.1 mapping)                            #
    # ---------------------------------------------------------------------- #

    def map_energy_level(self) -> int:
        """ROUND_HALF_UP(energy / 10.0), clamped 1..10."""
        raw = Decimal(str(self.signals.energy)) / Decimal("10")
        rounded = int(raw.to_integral_value(rounding=ROUND_HALF_UP))
        return max(1, min(10, rounded))

    def map_success_quality(self) -> int:
        """ROUND_HALF_UP(success / 10.0), clamped 0..10."""
        raw = Decimal(str(self.signals.success)) / Decimal("10")
        rounded = int(raw.to_integral_value(rounding=ROUND_HALF_UP))
        return max(0, min(10, rounded))

    def map_sentiment_score(self) -> float:
        """(valence - 50) / 50, rounded to 3 decimals, clamped [-1.0, 1.0]."""
        raw = (self.signals.valence - 50) / 50.0
        return max(-1.0, min(1.0, round(raw, 3)))

    def map_skills_themes_involved(self) -> list[str]:
        """
        skill_id first (if non-null), then theme_ids in order (Section 11.3.1).
        Returns [] when both are empty/null.
        """
        result: list[str] = []
        if self.skill_id is not None:
            result.append(self.skill_id)
        result.extend(self.theme_ids)
        return result


# Register with global registry
ContractRegistry.register("categorization", CategorizationContract)

__all__ = ["CategorizationContract", "CategorizationSignals"]
