"""
AI contract validation framework.

Implements Section 11.3 (Canonical JSON Contracts) from architecture.

All AI executors MUST return JSON that validates against the step contract
(Section 11.0.3). Unknown keys MUST be rejected, required fields enforced,
types checked strictly, and hashing must be deterministic (Section 11.0.4).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Type

from loguru import logger
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# --------------------------------------------------------------------------- #
# Exceptions                                                                   #
# --------------------------------------------------------------------------- #


class ContractValidationError(Exception):
    """Raised when AI output fails contract validation (Section 11.0.3)."""

    def __init__(self, step_name: str, message: str) -> None:
        self.step_name = step_name
        super().__init__(f"[contract:{step_name}] {message}")


# --------------------------------------------------------------------------- #
# Citation schema (Section 11.3.0.1)                                          #
# --------------------------------------------------------------------------- #


class CitationItem(BaseModel):
    """
    Canonical citation object schema (Section 11.3.0.1).

    Required keys: rag_document_id, chunk_id, score.
    Optional all-or-none provenance bundle: quote, char_start, char_end.
    """

    model_config = ConfigDict(extra="forbid")

    rag_document_id: str
    chunk_id: str
    score: float

    # Optional all-or-none provenance bundle
    quote: Optional[str] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None

    @field_validator("rag_document_id")
    @classmethod
    def _validate_rag_doc_id(cls, v: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", v):
            raise ValueError(f"rag_document_id must be 32-hex lowercase, got: {v!r}")
        return v

    @field_validator("chunk_id")
    @classmethod
    def _validate_chunk_id(cls, v: str) -> str:
        # Format: {rag_document_id}#chunk:{chunk_index}  (no padding)
        if not re.fullmatch(r"[0-9a-f]{32}#chunk:\d+", v):
            raise ValueError(
                f"chunk_id must match '{{32hex}}#chunk:{{n}}', got: {v!r}"
            )
        return v

    @field_validator("score")
    @classmethod
    def _validate_score_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("score must be a finite number")
        return v

    @field_validator("quote")
    @classmethod
    def _validate_quote_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (len(v) < 1 or len(v) > 300):
            raise ValueError("quote must be 1..300 code points")
        return v

    @field_validator("char_start")
    @classmethod
    def _validate_char_start(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("char_start must be >= 0")
        return v

    @model_validator(mode="after")
    def _validate_provenance_all_or_none(self) -> "CitationItem":
        """quote, char_start, char_end must all be present or all absent."""
        bundle = (self.quote, self.char_start, self.char_end)
        present = sum(1 for x in bundle if x is not None)
        if present not in (0, 3):
            raise ValueError(
                "Provenance bundle (quote, char_start, char_end) must be "
                "all-or-none: either all present or all absent"
            )
        if present == 3 and self.char_end <= self.char_start:  # type: ignore[operator]
            raise ValueError("char_end must be > char_start")
        return self

    @model_validator(mode="after")
    def _validate_chunk_id_prefix_matches_doc(self) -> "CitationItem":
        """chunk_id must be prefixed with rag_document_id."""
        if not self.chunk_id.startswith(self.rag_document_id):
            raise ValueError(
                f"chunk_id must start with rag_document_id "
                f"({self.rag_document_id!r}), got: {self.chunk_id!r}"
            )
        return self


# --------------------------------------------------------------------------- #
# Base contract                                                                 #
# --------------------------------------------------------------------------- #


class BaseAIContract(BaseModel):
    """
    Base class for all AI contracts (Section 11.0.3).

    Enforces:
    - extra='forbid' → unknown keys rejected
    - contract_version present on every subclass
    - citations present on every contract
    - Deterministic hashing (Section 11.0.4 JCS+NFC profile)
    """

    model_config = ConfigDict(extra="forbid")

    contract_version: int
    citations: List[CitationItem] = []

    def to_canonical_dict(self) -> dict:
        """Convert to canonical dictionary for hashing (NFC+JCS profile)."""
        return normalize_for_hashing(self.model_dump())

    def compute_hash(self) -> str:
        """
        Compute deterministic SHA-256 hash (Section 11.0.4 JCS+NFC profile).

        Steps:
        1. Normalize all strings to Unicode NFC
        2. Validate numbers are finite; normalize -0 → 0
        3. Serialize using RFC 8785 JCS rules (sort_keys, no whitespace)
        4. SHA-256 over UTF-8 bytes

        Returns lowercase hex SHA-256 hash.
        """
        canonical = self.to_canonical_dict()
        canonical_bytes = canonical_serialize_jcs(canonical)
        digest = hashlib.sha256(canonical_bytes).hexdigest()
        logger.debug(
            "[ai_contract] compute_hash step={} version={} hash={}",
            self.__class__.__name__,
            self.contract_version,
            digest[:16] + "...",
        )
        return digest


# --------------------------------------------------------------------------- #
# JCS+NFC canonicalization (Section 11.0.4)                                   #
# --------------------------------------------------------------------------- #


def normalize_for_hashing(data: Any) -> Any:
    """
    Normalize data for deterministic JCS+NFC hashing (Section 11.0.4).

    Rules:
    - str  → Unicode NFC normalization
    - int  → unchanged (int -0 is impossible)
    - float → -0.0 → 0; reject NaN / Infinity
    - dict  → recursively normalize keys + values
    - list  → preserve order, normalize elements
    - None / bool → unchanged
    """
    if isinstance(data, bool):
        # bool is a subclass of int; handle first to avoid misclassification
        return data

    if isinstance(data, str):
        return unicodedata.normalize("NFC", data)

    if isinstance(data, int):
        # Python int can never be -0; return as-is
        return data

    if isinstance(data, float):
        if math.isnan(data):
            raise ValueError("NaN is not allowed in canonical hash")
        if math.isinf(data):
            raise ValueError("Infinity is not allowed in canonical hash")
        # Normalize -0 to 0 (integer) so JSON serializes as "0" not "0.0"
        # Per Section 11.0.4: normalize -0 to 0
        if data == 0.0:
            return 0
        return data

    if isinstance(data, dict):
        # Check for duplicate keys is only meaningful when coming from raw JSON;
        # dict already deduplicates at parse time.
        return {
            normalize_for_hashing(k): normalize_for_hashing(v)
            for k, v in data.items()
        }

    if isinstance(data, list):
        return [normalize_for_hashing(item) for item in data]

    if data is None:
        return data

    raise ValueError(f"Unsupported type for canonical hashing: {type(data)!r}")


_EXPONENT_RE = re.compile(r"e([+-]?)0*(\d+)")


def _fix_exponent_notation(s: str) -> str:
    """
    Normalize Python's exponent notation to RFC 8785 / ES format.

    Python emits 'e-07'; JCS requires 'e-7' (no leading zeros in exponent).
    """
    return _EXPONENT_RE.sub(lambda m: f"e{m.group(1)}{m.group(2)}", s)


def canonical_serialize_jcs(data: Any) -> bytes:
    """
    Serialize value using RFC 8785 JCS rules (Section 11.0.4).

    JCS rules applied:
    - Object keys sorted lexicographically (UTF-16 code unit order per RFC 8785;
      Python sort approximates this for BMP characters)
    - No whitespace
    - UTF-8 encoding
    - Exponent notation normalized (e-07 → e-7) for ES6-compatible output

    Returns UTF-8 bytes of the canonical serialization.
    """
    raw = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,  # extra safety — NaN/Inf already rejected above
    )
    normalized = _fix_exponent_notation(raw)
    return normalized.encode("utf-8")


def canonical_hash(data: dict) -> str:
    """
    Compute deterministic SHA-256 hash using JCS+NFC profile (Section 11.0.4).

    Profile steps:
    1. Normalize all JSON strings (keys and values) to Unicode NFC
    2. Validate numbers are finite JSON numbers
    3. Normalize -0 to 0
    4. Serialize using RFC 8785 JCS rules
    5. Compute SHA-256 over UTF-8 bytes

    Returns lowercase hex SHA-256 hash.
    """
    normalized = normalize_for_hashing(data)
    raw_bytes = canonical_serialize_jcs(normalized)
    return hashlib.sha256(raw_bytes).hexdigest()


# --------------------------------------------------------------------------- #
# Contract registry                                                             #
# --------------------------------------------------------------------------- #


class ContractRegistry:
    """
    Registry of all AI contract classes (Section 11.0.3).

    Step names are the closed set defined in Section 11.0.2:
      categorization, quest_generation, insight_extraction,
      voice_transcription, report_generation, personality_message_generation
    """

    _contracts: Dict[str, Type[BaseAIContract]] = {}

    @classmethod
    def register(cls, step_name: str, contract_class: Type[BaseAIContract]) -> None:
        """Register a contract class for a pipeline step."""
        cls._contracts[step_name] = contract_class
        logger.debug(
            "[ai_contract] registered step={} class={}",
            step_name,
            contract_class.__name__,
        )

    @classmethod
    def get(cls, step_name: str) -> Type[BaseAIContract]:
        """Return the contract class registered for *step_name*."""
        if step_name not in cls._contracts:
            raise ValueError(f"No contract registered for step: {step_name!r}")
        return cls._contracts[step_name]

    @classmethod
    def validate(cls, step_name: str, data: dict) -> BaseAIContract:
        """
        Validate AI output dict against the registered contract for *step_name*.

        Logs validation events as required by Section 11.2.3 observability rules
        (using step_name, contract_version, and error codes — no raw payload).

        Args:
            step_name: Pipeline step name (e.g. 'categorization').
            data: AI output dictionary to validate.

        Returns:
            Validated contract instance.

        Raises:
            ContractValidationError: If validation fails.
        """
        contract_class = cls.get(step_name)
        contract_version = data.get("contract_version", "unknown")

        logger.info(
            "[ai_contract] validating step={} contract_version={}",
            step_name,
            contract_version,
        )

        try:
            instance = contract_class(**data)
        except Exception as exc:
            logger.error(
                "[ai_contract] validation_failed step={} contract_version={} "
                "error_code=CONTRACT_INVALID error={}",
                step_name,
                contract_version,
                str(exc),
            )
            raise ContractValidationError(step_name, str(exc)) from exc

        logger.info(
            "[ai_contract] validation_ok step={} contract_version={} "
            "input_hash={}",
            step_name,
            instance.contract_version,
            instance.compute_hash()[:16] + "...",
        )
        return instance

    @classmethod
    def validate_json(cls, step_name: str, raw_json: str) -> BaseAIContract:
        """
        Parse *raw_json* (LLM output string) then validate against contract.

        Detects duplicate keys in the raw JSON (Section 11.0.4 requirement)
        before handing off to Pydantic validation.

        Args:
            step_name: Pipeline step name.
            raw_json: Raw JSON string from LLM executor.

        Returns:
            Validated contract instance.

        Raises:
            ContractValidationError: If JSON is malformed, has duplicate keys,
                or fails contract validation.
        """
        logger.info(
            "[ai_contract] parsing_llm_output step={} payload_bytes={}",
            step_name,
            len(raw_json.encode("utf-8")),
        )

        # Detect duplicate keys (Section 11.0.4: MUST be rejected)
        seen_keys: list[str] = []

        def _raise_on_duplicate(pairs: list[tuple[str, Any]]) -> dict:
            keys = [k for k, _ in pairs]
            for k in keys:
                if keys.count(k) > 1 and k not in seen_keys:
                    seen_keys.append(k)
                    logger.error(
                        "[ai_contract] duplicate_key_rejected step={} key={}",
                        step_name,
                        k,
                    )
                    raise ContractValidationError(
                        step_name,
                        f"Duplicate object key rejected: {k!r}",
                    )
            return dict(pairs)

        try:
            data = json.loads(raw_json, object_pairs_hook=_raise_on_duplicate)
        except ContractValidationError:
            raise
        except json.JSONDecodeError as exc:
            logger.error(
                "[ai_contract] json_parse_failed step={} error={}",
                step_name,
                str(exc),
            )
            raise ContractValidationError(
                step_name, f"Invalid JSON: {exc}"
            ) from exc

        return cls.validate(step_name, data)


# --------------------------------------------------------------------------- #
# Public re-exports                                                            #
# --------------------------------------------------------------------------- #

__all__ = [
    "BaseAIContract",
    "CitationItem",
    "ContractRegistry",
    "ContractValidationError",
    "canonical_hash",
    "canonical_serialize_jcs",
    "normalize_for_hashing",
]
