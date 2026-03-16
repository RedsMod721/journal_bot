"""
Quest generation contract (v3) — Section 11.3.2.

Output schema:
{
  "contract_version": 3,
  "new_quests": [],
  "progress_updates_schema_version": 1,
  "progress_updates": [],
  "citations": []
}

Constraints (Section 11.3.2):
- new_quests: max 12 items
- progress_updates_schema_version: MUST equal 1 in this spec
- progress_updates: max 50 items, union of 4 variants discriminated by update_kind
- XP authority is server-side (Section 10); contracts MUST NOT include XP amounts
"""

from __future__ import annotations

import re
from typing import Annotated, List, Literal, Optional, Union

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.ai.contracts import BaseAIContract, CitationItem, ContractRegistry

_HEX32_RE = re.compile(r"^[0-9a-f]{32}$")


def _is_valid_quest_id(v: str) -> bool:
    return bool(_HEX32_RE.match(v))


# --------------------------------------------------------------------------- #
# new_quests[] item schema                                                     #
# --------------------------------------------------------------------------- #


class NewQuestItem(BaseModel):
    """
    New quest proposal item (Section 11.3.2).

    XP is NOT included — computed server-side by Section 10 rules.
    """

    model_config = ConfigDict(extra="forbid")

    quest_type: Literal["instant", "longterm"]
    completion_type: Literal["one_time", "cumulative", "recursive", "streak"]
    title: str = Field(..., min_length=1, max_length=80)
    description: str = Field(..., min_length=1, max_length=400)
    due_at_utc_ms: int = Field(..., ge=0)
    expires_at_utc_ms: Optional[int] = None

    @model_validator(mode="after")
    def _validate_expiry(self) -> "NewQuestItem":
        if (
            self.expires_at_utc_ms is not None
            and self.expires_at_utc_ms < self.due_at_utc_ms
        ):
            raise ValueError(
                f"expires_at_utc_ms ({self.expires_at_utc_ms}) must be "
                f">= due_at_utc_ms ({self.due_at_utc_ms})"
            )
        return self


# --------------------------------------------------------------------------- #
# progress_updates[] — schema version 1 — union by update_kind                #
# --------------------------------------------------------------------------- #


class OneTimeMarkUpdate(BaseModel):
    """Variant A: one_time_mark (Section 11.3.2)."""

    model_config = ConfigDict(extra="forbid")

    update_kind: Literal["one_time_mark"]
    quest_id: str
    completed_at_utc_ms: int = Field(..., ge=0)

    @field_validator("quest_id")
    @classmethod
    def _validate_quest_id(cls, v: str) -> str:
        if not _is_valid_quest_id(v):
            raise ValueError(f"quest_id must be 32-hex lowercase, got: {v!r}")
        return v


class CumulativeDeltaUpdate(BaseModel):
    """Variant B: cumulative_delta (Section 11.3.2)."""

    model_config = ConfigDict(extra="forbid")

    update_kind: Literal["cumulative_delta"]
    quest_id: str
    delta: int = Field(..., ge=-100000, le=100000)
    event_at_utc_ms: int = Field(..., ge=0)

    @field_validator("quest_id")
    @classmethod
    def _validate_quest_id(cls, v: str) -> str:
        if not _is_valid_quest_id(v):
            raise ValueError(f"quest_id must be 32-hex lowercase, got: {v!r}")
        return v


class StreakEventUpdate(BaseModel):
    """Variant C: streak_event (Section 11.3.2)."""

    model_config = ConfigDict(extra="forbid")

    update_kind: Literal["streak_event"]
    quest_id: str
    event: Literal["increment", "reset", "break"]
    event_at_utc_ms: int = Field(..., ge=0)

    @field_validator("quest_id")
    @classmethod
    def _validate_quest_id(cls, v: str) -> str:
        if not _is_valid_quest_id(v):
            raise ValueError(f"quest_id must be 32-hex lowercase, got: {v!r}")
        return v


class RecursiveOccurrenceUpdate(BaseModel):
    """Variant D: recursive_occurrence (Section 11.3.2)."""

    model_config = ConfigDict(extra="forbid")

    update_kind: Literal["recursive_occurrence"]
    quest_id: str
    occurrence_at_utc_ms: int = Field(..., ge=0)
    occurrence_key: str = Field(..., min_length=1, max_length=80)

    @field_validator("quest_id")
    @classmethod
    def _validate_quest_id(cls, v: str) -> str:
        if not _is_valid_quest_id(v):
            raise ValueError(f"quest_id must be 32-hex lowercase, got: {v!r}")
        return v


# Discriminated union — Pydantic v2 style
ProgressUpdate = Annotated[
    Union[
        OneTimeMarkUpdate,
        CumulativeDeltaUpdate,
        StreakEventUpdate,
        RecursiveOccurrenceUpdate,
    ],
    Field(discriminator="update_kind"),
]


# --------------------------------------------------------------------------- #
# Quest generation contract                                                    #
# --------------------------------------------------------------------------- #


class QuestGenerationContract(BaseAIContract):
    """
    Quest generation contract (v3) — Section 11.3.2.

    Required keys: contract_version, new_quests, progress_updates_schema_version,
    progress_updates, citations.
    """

    contract_version: Literal[3] = 3

    new_quests: List[NewQuestItem] = Field(default_factory=list, max_length=12)
    progress_updates_schema_version: Literal[1]
    progress_updates: List[ProgressUpdate] = Field(
        default_factory=list, max_length=50
    )
    citations: List[CitationItem] = Field(default_factory=list)

    @field_validator("new_quests")
    @classmethod
    def _validate_new_quests_max(cls, v: List[NewQuestItem]) -> List[NewQuestItem]:
        if len(v) > 12:
            raise ValueError(f"new_quests max 12 items, got {len(v)}")
        return v

    @field_validator("progress_updates")
    @classmethod
    def _validate_progress_updates_max(
        cls, v: List[ProgressUpdate]
    ) -> List[ProgressUpdate]:
        if len(v) > 50:
            raise ValueError(f"progress_updates max 50 items, got {len(v)}")
        return v

    @model_validator(mode="after")
    def _log_contract_loaded(self) -> "QuestGenerationContract":
        rag_backed = len(self.citations) > 0

        logger.info(
            "[ai_contract][quest_generation][pipeline_step] validated "
            "new_quests={} progress_updates={} schema_version={} "
            "citations_count={} rag_backed={}",
            len(self.new_quests),
            len(self.progress_updates),
            self.progress_updates_schema_version,
            len(self.citations),
            rag_backed,
        )

        if self.new_quests:
            type_counts: dict[str, int] = {}
            for q in self.new_quests:
                key = f"{q.quest_type}/{q.completion_type}"
                type_counts[key] = type_counts.get(key, 0) + 1
            logger.debug(
                "[ai_contract][quest_generation][llm] new quest proposals "
                "by_type={}",
                type_counts,
            )
        else:
            logger.debug(
                "[ai_contract][quest_generation][llm] no new quests proposed"
            )

        if self.progress_updates:
            kind_counts: dict[str, int] = {}
            for u in self.progress_updates:
                kind_counts[u.update_kind] = kind_counts.get(u.update_kind, 0) + 1
            logger.debug(
                "[ai_contract][quest_generation][pipeline_step] progress update "
                "variants by_kind={}",
                kind_counts,
            )

        if rag_backed:
            doc_ids = list({c.rag_document_id for c in self.citations})
            logger.debug(
                "[ai_contract][quest_generation][rag] citations present "
                "unique_documents={} chunk_ids={}",
                len(doc_ids),
                [c.chunk_id for c in self.citations],
            )
        else:
            logger.debug(
                "[ai_contract][quest_generation][rag] no citations — "
                "quest generation ran without RAG retrieval"
            )

        return self


# Register with global registry
ContractRegistry.register("quest_generation", QuestGenerationContract)

__all__ = [
    "QuestGenerationContract",
    "NewQuestItem",
    "OneTimeMarkUpdate",
    "CumulativeDeltaUpdate",
    "StreakEventUpdate",
    "RecursiveOccurrenceUpdate",
]
