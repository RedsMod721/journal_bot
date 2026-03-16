"""
Voice transcription contract (v1) — Section 11.3.4.

Output schema:
{
  "contract_version": 1,
  "transcript_text": "Today I felt focused after lunch...",
  "confidence_0_1": 0.93,
  "language": "en",
  "segments": [
    { "start_ms": 0, "end_ms": 1200, "text": "Today I felt focused", "confidence_0_1": 0.92 }
  ],
  "citations": []
}

Constraints (Section 11.3.4):
- transcript_text: 0..12000 code points (may be empty for silent/unintelligible audio)
- confidence_0_1: [0.0, 1.0]
- language: BCP-47, lowercase preferred, 2..35 chars
- segments: max 500, sorted by start_ms ASC, no overlaps
- citations: MUST be [] (RAG not used for transcription)

Persistence mapping (Section 11.3.4):
  journal_entries.content       <- normalized transcript_text
  journal_entries.transcription_confidence <- confidence_0_1
  journal_entries.entry_type    <- keep 'audio'
  language + segments           <- telemetry-only
"""

from __future__ import annotations

import unicodedata
from typing import List, Literal, Optional

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.ai.contracts import BaseAIContract, CitationItem, ContractRegistry


# --------------------------------------------------------------------------- #
# Segment item                                                                 #
# --------------------------------------------------------------------------- #


class TranscriptSegment(BaseModel):
    """
    Single transcript segment (Section 11.3.4).

    confidence_0_1 is OPTIONAL at the segment level.
    """

    model_config = ConfigDict(extra="forbid")

    start_ms: int = Field(..., ge=0)
    end_ms: int
    text: str = Field(..., min_length=1, max_length=400)
    confidence_0_1: Optional[float] = None

    @model_validator(mode="after")
    def _validate_end_after_start(self) -> "TranscriptSegment":
        if self.end_ms <= self.start_ms:
            raise ValueError(
                f"end_ms ({self.end_ms}) must be > start_ms ({self.start_ms})"
            )
        return self

    @field_validator("confidence_0_1")
    @classmethod
    def _validate_confidence(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValueError(
                f"confidence_0_1 must be in [0.0, 1.0], got: {v}"
            )
        return v


# --------------------------------------------------------------------------- #
# Voice transcription contract                                                 #
# --------------------------------------------------------------------------- #


class VoiceTranscriptionContract(BaseAIContract):
    """
    Voice transcription contract (v1) — Section 11.3.4.

    Required keys: contract_version, transcript_text, confidence_0_1, language,
    segments, citations.
    """

    contract_version: Literal[1] = 1

    # transcript_text may be empty for silent/unintelligible audio
    transcript_text: str = Field(..., max_length=12000)
    confidence_0_1: float = Field(..., ge=0.0, le=1.0)
    language: str = Field(..., min_length=2, max_length=35)
    segments: List[TranscriptSegment] = Field(default_factory=list, max_length=500)
    citations: List[CitationItem] = Field(default_factory=list)

    @field_validator("language")
    @classmethod
    def _normalize_language(cls, v: str) -> str:
        """Server MAY normalize BCP-47 tag to lowercase (Section 11.3.4)."""
        return v.lower()

    @field_validator("segments")
    @classmethod
    def _validate_segments_ordering_and_overlap(
        cls, v: List[TranscriptSegment]
    ) -> List[TranscriptSegment]:
        """
        Segments MUST be sorted by start_ms ASC and MUST NOT overlap.
        segment[i].end_ms <= segment[i+1].start_ms (Section 11.3.4).
        """
        for i in range(len(v) - 1):
            if v[i].start_ms > v[i + 1].start_ms:
                logger.error(
                    "[ai_contract][voice_transcription][pipeline_step] "
                    "segment_ordering_violation "
                    "segment_index={} start_ms={} next_start_ms={} "
                    "error_code=SEGMENT_ORDER_INVALID",
                    i,
                    v[i].start_ms,
                    v[i + 1].start_ms,
                )
                raise ValueError(
                    f"segments must be sorted by start_ms ASC; "
                    f"segment[{i}].start_ms={v[i].start_ms} > "
                    f"segment[{i+1}].start_ms={v[i+1].start_ms}"
                )
            if v[i].end_ms > v[i + 1].start_ms:
                logger.error(
                    "[ai_contract][voice_transcription][pipeline_step] "
                    "segment_overlap_violation "
                    "segment_index={} end_ms={} next_start_ms={} "
                    "error_code=SEGMENT_OVERLAP",
                    i,
                    v[i].end_ms,
                    v[i + 1].start_ms,
                )
                raise ValueError(
                    f"segments must not overlap; "
                    f"segment[{i}].end_ms={v[i].end_ms} > "
                    f"segment[{i+1}].start_ms={v[i+1].start_ms}"
                )
        return v

    @model_validator(mode="after")
    def _validate_segments_text_is_substring(self) -> "VoiceTranscriptionContract":
        """
        If segments is non-empty, concatenating segment texts with spaces MUST be
        a substring of transcript_text after NFC + whitespace normalization
        (Section 11.3.4).
        """
        if not self.segments:
            return self

        def _norm(s: str) -> str:
            nfc = unicodedata.normalize("NFC", s)
            return " ".join(nfc.split())

        concat = _norm(" ".join(seg.text for seg in self.segments))
        transcript_norm = _norm(self.transcript_text)

        if concat not in transcript_norm:
            logger.error(
                "[ai_contract][voice_transcription][pipeline_step] "
                "segment_text_not_in_transcript "
                "segments_count={} concat_len={} transcript_len={} "
                "error_code=SEGMENT_TEXT_MISMATCH",
                len(self.segments),
                len(concat),
                len(transcript_norm),
            )
            raise ValueError(
                "Concatenated segment texts must be a substring of "
                "transcript_text after NFC + whitespace normalization"
            )
        return self

    @model_validator(mode="after")
    def _warn_rag_citations_present(self) -> "VoiceTranscriptionContract":
        """
        RAG is NOT used for transcription (Section 11.3.4). Log a warning if
        citations is non-empty so the caller can detect LLM prompt leakage.
        """
        if self.citations:
            logger.warning(
                "[ai_contract][voice_transcription][rag] "
                "unexpected_citations_in_transcription "
                "citations_count={} "
                "note=RAG_not_used_for_transcription",
                len(self.citations),
            )
        return self

    @model_validator(mode="after")
    def _warn_empty_transcript(self) -> "VoiceTranscriptionContract":
        """Log when transcript is empty — may indicate silent/unintelligible audio."""
        if not self.transcript_text:
            logger.warning(
                "[ai_contract][voice_transcription][llm] "
                "empty_transcript_text "
                "confidence={:.3f} language={} segments={} "
                "note=may_indicate_silent_or_unintelligible_audio",
                self.confidence_0_1,
                self.language,
                len(self.segments),
            )
        return self

    @model_validator(mode="after")
    def _log_contract_loaded(self) -> "VoiceTranscriptionContract":
        logger.debug(
            "[ai_contract][voice_transcription][pipeline_step] loaded "
            "transcript_len={} confidence={:.3f} language={} segments={} citations={}",
            len(self.transcript_text),
            self.confidence_0_1,
            self.language,
            len(self.segments),
            len(self.citations),
        )
        return self

    # ---------------------------------------------------------------------- #
    # Persistence helpers (Section 11.3.4)                                    #
    # ---------------------------------------------------------------------- #

    def normalized_transcript(self) -> str:
        """
        Apply persistence normalization rules (Section 11.3.4):
        - Unicode NFC
        - Collapse all Unicode whitespace to ASCII space, trim ends
        - Collapse multiple spaces to one
        - Preserve paragraph breaks: runs of 2+ newlines → exactly \\n\\n
        - Cap at 10000 Unicode code points (truncate if needed)
        """
        import re as _re

        text = unicodedata.normalize("NFC", self.transcript_text)
        # Preserve paragraph breaks first
        text = _re.sub(r"\n{2,}", "\n\n", text)
        # Collapse horizontal whitespace (not newlines)
        text = _re.sub(r"[^\S\n]+", " ", text)
        text = text.strip()
        # Cap at 10000 code points
        if len(text) > 10000:
            logger.warning(
                "[ai_contract][voice_transcription] transcript truncated "
                "from {} to 10000 code points",
                len(text),
            )
            text = text[:10000]
        return text


# Register with global registry
ContractRegistry.register("voice_transcription", VoiceTranscriptionContract)

__all__ = ["VoiceTranscriptionContract", "TranscriptSegment"]
