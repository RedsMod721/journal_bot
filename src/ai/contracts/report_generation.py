"""
Report generation contract (v1) — Section 11.3.5.

Output schema:
{
  "contract_version": 1,
  "report_kind": "weekly",
  "summary": "This week you were consistent and improved energy stability.",
  "sections": [
    { "title": "Highlights", "bullets": ["3 strong work sessions", "2 workouts"] }
  ],
  "citations": []
}

Constraints (Section 11.3.5):
- report_kind: closed enum — daily | weekly | monthly
- summary: 1..1200 code points
- sections: max 12, ordering meaningful (preserve as returned)
- Each section: title 1..80, bullets max 12, each 1..160
- citations: MUST be present

File artifacts (MUST): handled out-of-band by server; NOT embedded in this contract.
"""

from __future__ import annotations

from typing import List, Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.ai.contracts import BaseAIContract, CitationItem, ContractRegistry


# --------------------------------------------------------------------------- #
# Section item                                                                 #
# --------------------------------------------------------------------------- #


class ReportSection(BaseModel):
    """Single section in a report (Section 11.3.5)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=80)
    bullets: List[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def _validate_bullets(self) -> "ReportSection":
        for idx, bullet in enumerate(self.bullets):
            if len(bullet) < 1 or len(bullet) > 160:
                logger.error(
                    "[ai_contract][report_generation][llm] "
                    "bullet_length_violation "
                    "section_title={!r} bullet_index={} bullet_len={} "
                    "error_code=BULLET_LENGTH_INVALID",
                    self.title,
                    idx,
                    len(bullet),
                )
                raise ValueError(
                    f"Each bullet must be 1..160 code points, "
                    f"got {len(bullet)}: {bullet!r}"
                )
        return self


# --------------------------------------------------------------------------- #
# Report generation contract                                                   #
# --------------------------------------------------------------------------- #


class ReportGenerationContract(BaseAIContract):
    """
    Report generation contract (v1) — Section 11.3.5.

    Required keys: contract_version, report_kind, summary, sections, citations.
    Section order is meaningful and MUST be preserved.
    """

    contract_version: Literal[1] = 1

    report_kind: Literal["daily", "weekly", "monthly"]
    summary: str = Field(..., min_length=1, max_length=1200)
    sections: List[ReportSection] = Field(default_factory=list, max_length=12)
    citations: List[CitationItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _warn_empty_sections(self) -> "ReportGenerationContract":
        """Log a warning when the LLM returned no structured sections."""
        if not self.sections:
            logger.warning(
                "[ai_contract][report_generation][llm] "
                "empty_sections_in_report "
                "report_kind={} summary_len={} "
                "note=LLM_returned_no_structured_sections",
                self.report_kind,
                len(self.summary),
            )
        return self

    @model_validator(mode="after")
    def _log_rag_citations(self) -> "ReportGenerationContract":
        """Log when RAG citations are present so the pipeline step is traceable."""
        if self.citations:
            logger.debug(
                "[ai_contract][report_generation][rag] "
                "citations_present "
                "report_kind={} citations_count={}",
                self.report_kind,
                len(self.citations),
            )
        return self

    @model_validator(mode="after")
    def _log_contract_loaded(self) -> "ReportGenerationContract":
        logger.debug(
            "[ai_contract][report_generation][pipeline_step] loaded "
            "report_kind={} sections={} total_bullets={} citations={}",
            self.report_kind,
            len(self.sections),
            sum(len(s.bullets) for s in self.sections),
            len(self.citations),
        )
        return self


# Register with global registry
ContractRegistry.register("report_generation", ReportGenerationContract)

__all__ = ["ReportGenerationContract", "ReportSection"]
