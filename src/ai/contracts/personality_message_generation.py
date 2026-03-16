"""
Personality message generation contract (v2) — Section 11.3.6.

Output schema:
{
  "contract_version": 2,
  "message_type": "quest_complete",
  "personality": "raphael",
  "text": "Nice work. You closed out your goals without forcing it.",
  "context_data": { "quest_ids": ["44444444444444444444444444444444"] },
  "citations": []
}

context_data is discriminated by message_type (Section 11.3.6):
  entry_ack      → {}
  quest_complete → { "quest_ids": [<1..25 quest_ids>] }
  quest_nudge    → { "quest_ids": [<1..25 quest_ids>] }
  report_summary → { "report_kind": "daily|weekly|monthly" }

Exactly-once logical slot rule (Section 11.3.6):
  Persisted row MUST use the REQUESTED personality even if fallback content is used.
  Fallback MUST NOT switch persisted personality to a different value.

quest_complete aggregation rule (Section 11.3.6):
  Messages aggregated per entry. Persist quest_id=NULL, store ids in
  context_data.quest_ids[].
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from loguru import logger
from pydantic import ConfigDict, Field, field_validator, model_validator

from src.ai.contracts import BaseAIContract, CitationItem, ContractRegistry

_HEX32_RE = re.compile(r"^[0-9a-f]{32}$")


def _is_valid_quest_id(v: str) -> bool:
    return bool(_HEX32_RE.match(v))


# --------------------------------------------------------------------------- #
# Personality message generation contract                                      #
# --------------------------------------------------------------------------- #


class PersonalityMessageGenerationContract(BaseAIContract):
    """
    Personality message generation contract (v2) — Section 11.3.6.

    Required keys: contract_version, message_type, personality, text,
    context_data, citations.
    """

    contract_version: Literal[2] = 2

    message_type: Literal["entry_ack", "quest_complete", "quest_nudge", "report_summary"]
    personality: Literal["raphael", "therapist", "observer"]
    text: str = Field(..., min_length=1, max_length=2000)
    context_data: Dict[str, Any]
    citations: List[CitationItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_context_data(self) -> "PersonalityMessageGenerationContract":
        """
        Validate context_data based on message_type (Section 11.3.6).

        Unknown keys are rejected for each variant.
        """
        cd = self.context_data
        mt = self.message_type

        if mt == "entry_ack":
            if cd != {}:
                logger.error(
                    "[ai_contract][personality_message_generation][pipeline_step] "
                    "context_data_violation "
                    "message_type=entry_ack unexpected_keys={} "
                    "error_code=CONTEXT_DATA_NOT_EMPTY",
                    list(cd.keys()),
                )
                raise ValueError(
                    f"context_data for entry_ack must be {{}}, got: {cd!r}"
                )

        elif mt in ("quest_complete", "quest_nudge"):
            allowed_keys = {"quest_ids"}
            extra = set(cd.keys()) - allowed_keys
            if extra:
                logger.error(
                    "[ai_contract][personality_message_generation][pipeline_step] "
                    "context_data_unknown_keys "
                    "message_type={} unknown_keys={} "
                    "error_code=CONTEXT_DATA_UNKNOWN_KEYS",
                    mt,
                    sorted(extra),
                )
                raise ValueError(
                    f"Unknown keys in context_data for {mt}: {extra}"
                )
            quest_ids = cd.get("quest_ids")
            if quest_ids is None:
                logger.error(
                    "[ai_contract][personality_message_generation][pipeline_step] "
                    "context_data_missing_quest_ids "
                    "message_type={} error_code=CONTEXT_DATA_MISSING_FIELD",
                    mt,
                )
                raise ValueError(
                    f"context_data for {mt} must contain 'quest_ids'"
                )
            if not isinstance(quest_ids, list):
                logger.error(
                    "[ai_contract][personality_message_generation][pipeline_step] "
                    "context_data_quest_ids_not_list "
                    "message_type={} actual_type={} error_code=CONTEXT_DATA_TYPE_ERROR",
                    mt,
                    type(quest_ids).__name__,
                )
                raise ValueError(
                    f"context_data.quest_ids must be a list, got {type(quest_ids)}"
                )
            if len(quest_ids) < 1 or len(quest_ids) > 25:
                logger.error(
                    "[ai_contract][personality_message_generation][pipeline_step] "
                    "context_data_quest_ids_count_invalid "
                    "message_type={} count={} error_code=CONTEXT_DATA_COUNT_INVALID",
                    mt,
                    len(quest_ids),
                )
                raise ValueError(
                    f"context_data.quest_ids must have 1..25 items, got {len(quest_ids)}"
                )
            for qid in quest_ids:
                if not isinstance(qid, str) or not _is_valid_quest_id(qid):
                    logger.error(
                        "[ai_contract][personality_message_generation][pipeline_step] "
                        "context_data_invalid_quest_id "
                        "message_type={} quest_id={!r} "
                        "error_code=CONTEXT_DATA_INVALID_QUEST_ID",
                        mt,
                        qid,
                    )
                    raise ValueError(
                        f"Each quest_id must be 32-hex lowercase, got: {qid!r}"
                    )

        elif mt == "report_summary":
            allowed_keys = {"report_kind"}
            extra = set(cd.keys()) - allowed_keys
            if extra:
                logger.error(
                    "[ai_contract][personality_message_generation][pipeline_step] "
                    "context_data_unknown_keys "
                    "message_type=report_summary unknown_keys={} "
                    "error_code=CONTEXT_DATA_UNKNOWN_KEYS",
                    sorted(extra),
                )
                raise ValueError(
                    f"Unknown keys in context_data for report_summary: {extra}"
                )
            report_kind = cd.get("report_kind")
            if report_kind not in ("daily", "weekly", "monthly"):
                logger.error(
                    "[ai_contract][personality_message_generation][pipeline_step] "
                    "context_data_invalid_report_kind "
                    "message_type=report_summary report_kind={!r} "
                    "error_code=CONTEXT_DATA_INVALID_REPORT_KIND",
                    report_kind,
                )
                raise ValueError(
                    f"context_data.report_kind must be daily|weekly|monthly, "
                    f"got: {report_kind!r}"
                )

        return self

    @model_validator(mode="after")
    def _log_rag_citations(self) -> "PersonalityMessageGenerationContract":
        """Log when RAG citations are present — personality messages may use RAG."""
        if self.citations:
            logger.debug(
                "[ai_contract][personality_message_generation][rag] "
                "citations_present "
                "message_type={} personality={} citations_count={}",
                self.message_type,
                self.personality,
                len(self.citations),
            )
        return self

    @model_validator(mode="after")
    def _warn_long_message_text(self) -> "PersonalityMessageGenerationContract":
        """Warn when the LLM-generated message text approaches the 2000-char cap."""
        text_len = len(self.text)
        if text_len > 1800:
            logger.warning(
                "[ai_contract][personality_message_generation][llm] "
                "message_text_near_max_length "
                "message_type={} personality={} text_len={} max=2000 "
                "note=LLM_output_may_be_truncated_or_verbose",
                self.message_type,
                self.personality,
                text_len,
            )
        return self

    @model_validator(mode="after")
    def _log_contract_loaded(self) -> "PersonalityMessageGenerationContract":
        logger.debug(
            "[ai_contract][personality_message_generation][pipeline_step] loaded "
            "message_type={} personality={} text_len={} citations={}",
            self.message_type,
            self.personality,
            len(self.text),
            len(self.citations),
        )
        return self


# Register with global registry
ContractRegistry.register(
    "personality_message_generation", PersonalityMessageGenerationContract
)

__all__ = ["PersonalityMessageGenerationContract"]
