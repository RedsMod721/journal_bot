"""
Insight extraction contract (v1) — Section 11.3.3.

Output schema:
{
  "contract_version": 1,
  "insights": [
    {
      "title": "You focus better after a walk",
      "body": "On days you walk before work, your journaling shows higher clarity."
    }
  ],
  "citations": []
}

Constraints (Section 11.3.3):
- insights: max 10 items; ordering is meaningful (highest relevance first)
- Each insight: title 1..120, body 1..800; unknown keys rejected
- citations: MUST be present; [] when no retrieval was used
"""

from __future__ import annotations

from typing import List, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.ai.contracts import BaseAIContract, CitationItem, ContractRegistry


# --------------------------------------------------------------------------- #
# Insight item                                                                 #
# --------------------------------------------------------------------------- #


class InsightItem(BaseModel):
    """Single insight item (Section 11.3.3)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=800)


# --------------------------------------------------------------------------- #
# Insight extraction contract                                                  #
# --------------------------------------------------------------------------- #


class InsightExtractionContract(BaseAIContract):
    """
    Insight extraction contract (v1) — Section 11.3.3.

    Required keys: contract_version, insights, citations.
    Ordering of insights[] is meaningful and MUST be preserved (highest relevance first).
    """

    contract_version: Literal[1] = 1

    insights: List[InsightItem] = Field(default_factory=list, max_length=10)
    citations: List[CitationItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _log_contract_loaded(self) -> "InsightExtractionContract":
        rag_backed = len(self.citations) > 0

        logger.info(
            "[ai_contract][insight_extraction][pipeline_step] validated "
            "insights_count={} citations_count={} rag_backed={}",
            len(self.insights),
            len(self.citations),
            rag_backed,
        )

        if not self.insights:
            # LLM returned no insights — pipeline degradation signal
            logger.warning(
                "[ai_contract][insight_extraction][llm] empty insights list — "
                "LLM may have found no patterns or degraded silently"
            )

        if rag_backed:
            doc_ids = list({c.rag_document_id for c in self.citations})
            logger.debug(
                "[ai_contract][insight_extraction][rag] citations present "
                "unique_documents={} chunk_ids={}",
                len(doc_ids),
                [c.chunk_id for c in self.citations],
            )
        else:
            logger.debug(
                "[ai_contract][insight_extraction][rag] no citations — "
                "insight extraction ran without RAG retrieval"
            )

        for i, insight in enumerate(self.insights):
            logger.debug(
                "[ai_contract][insight_extraction][llm] insight rank={} "
                "title_len={} body_len={}",
                i,
                len(insight.title),
                len(insight.body),
            )

        return self


# Register with global registry
ContractRegistry.register("insight_extraction", InsightExtractionContract)

__all__ = ["InsightExtractionContract", "InsightItem"]
