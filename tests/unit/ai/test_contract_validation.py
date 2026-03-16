"""
Tests for AI contract validation framework (Section 11).

Covers:
- BaseAIContract: unknown key rejection, contract_version enforcement
- CitationItem: all-or-none provenance, chunk_id format, rag_document_id
- Deterministic hashing (JCS+NFC profile) — test vectors from Section 11.0.4
- ContractRegistry: register, get, validate, validate_json
- Categorization (v1) — Section 11.3.1
- QuestGeneration (v3) — Section 11.3.2
- InsightExtraction (v1) — Section 11.3.3
- VoiceTranscription (v1) — Section 11.3.4
- ReportGeneration (v1) — Section 11.3.5
- PersonalityMessageGeneration (v2) — Section 11.3.6
- Error handling: ContractValidationError, duplicate keys in JSON
"""

from __future__ import annotations

import hashlib
import json

import pytest

# Force contract registration by importing all contract modules
from src.ai.contracts import (
    BaseAIContract,
    CitationItem,
    ContractRegistry,
    ContractValidationError,
    canonical_hash,
    canonical_serialize_jcs,
    normalize_for_hashing,
)
from src.ai.contracts.categorization import CategorizationContract
from src.ai.contracts.insight_extraction import InsightExtractionContract
from src.ai.contracts.personality_message_generation import (
    PersonalityMessageGenerationContract,
)
from src.ai.contracts.quest_generation import (
    CumulativeDeltaUpdate,
    NewQuestItem,
    OneTimeMarkUpdate,
    QuestGenerationContract,
    RecursiveOccurrenceUpdate,
    StreakEventUpdate,
)
from src.ai.contracts.report_generation import ReportGenerationContract, ReportSection
from src.ai.contracts.voice_transcription import (
    TranscriptSegment,
    VoiceTranscriptionContract,
)

# =========================================================================== #
# Helper fixtures / factories                                                  #
# =========================================================================== #

_SKILL_ID = "33333333333333333333333333333333"
_THEME_ID_1 = "11111111111111111111111111111111"
_THEME_ID_2 = "22222222222222222222222222222222"
_QUEST_ID = "44444444444444444444444444444444"
_RAG_DOC_ID = "aabbccdd11223344aabbccdd11223344"


def _citation() -> dict:
    return {
        "rag_document_id": _RAG_DOC_ID,
        "chunk_id": f"{_RAG_DOC_ID}#chunk:0",
        "score": 0.91,
    }


def _base_categorization(**overrides) -> dict:
    data = {
        "contract_version": 1,
        "skill_id": _SKILL_ID,
        "theme_ids": [_THEME_ID_1],
        "tags": ["focus", "work"],
        "signals": {"energy": 76, "valence": 58, "success": 70},
        "citations": [],
    }
    data.update(overrides)
    return data


def _base_quest_generation(**overrides) -> dict:
    data = {
        "contract_version": 3,
        "new_quests": [],
        "progress_updates_schema_version": 1,
        "progress_updates": [],
        "citations": [],
    }
    data.update(overrides)
    return data


def _base_insight_extraction(**overrides) -> dict:
    data = {
        "contract_version": 1,
        "insights": [{"title": "You focus better after a walk", "body": "On days you walk..."}],
        "citations": [],
    }
    data.update(overrides)
    return data


def _base_voice_transcription(**overrides) -> dict:
    data = {
        "contract_version": 1,
        "transcript_text": "Today I felt focused after lunch.",
        "confidence_0_1": 0.93,
        "language": "en",
        "segments": [],
        "citations": [],
    }
    data.update(overrides)
    return data


def _base_report_generation(**overrides) -> dict:
    data = {
        "contract_version": 1,
        "report_kind": "weekly",
        "summary": "This week you were consistent.",
        "sections": [{"title": "Highlights", "bullets": ["3 strong work sessions"]}],
        "citations": [],
    }
    data.update(overrides)
    return data


def _base_personality_message(**overrides) -> dict:
    data = {
        "contract_version": 2,
        "message_type": "entry_ack",
        "personality": "raphael",
        "text": "Nice entry today.",
        "context_data": {},
        "citations": [],
    }
    data.update(overrides)
    return data


# =========================================================================== #
# Section 11.0.4 — Deterministic hashing test vectors                         #
# =========================================================================== #


class TestDeterministicHashing:
    """Test vectors from Section 11.0.4 (JCS+NFC profile)."""

    def test_vector_numeric_0_1(self):
        """{"n": 0.1} → c20c34ed..."""
        serialized = canonical_serialize_jcs(normalize_for_hashing({"n": 0.1}))
        assert serialized == b'{"n":0.1}'
        digest = hashlib.sha256(serialized).hexdigest()
        assert digest == "c20c34ed16c837e86b4dcdb33f98c274c9f7da1231f64302082d2cd50743f951"

    def test_vector_numeric_1e_minus_7(self):
        """{"n": 1e-7} → 747d6d23..."""
        serialized = canonical_serialize_jcs(normalize_for_hashing({"n": 1e-7}))
        assert serialized == b'{"n":1e-7}'
        digest = hashlib.sha256(serialized).hexdigest()
        assert digest == "747d6d23b64d1b2d579adb832b44de31c91c875bbef7a8e397f5d183a746b54b"

    def test_vector_numeric_1e21(self):
        """{"n": 1e21} → f1ee2b60..."""
        serialized = canonical_serialize_jcs(normalize_for_hashing({"n": 1e21}))
        assert serialized == b'{"n":1e+21}'
        digest = hashlib.sha256(serialized).hexdigest()
        assert digest == "f1ee2b60ee95a3170fdc07a577e5f3514ced26867443d69da265acadead81007"

    def test_vector_numeric_1234567890_123456(self):
        """{"n": 1234567890.123456} → 5a04cc11..."""
        serialized = canonical_serialize_jcs(
            normalize_for_hashing({"n": 1234567890.123456})
        )
        assert serialized == b'{"n":1234567890.123456}'
        digest = hashlib.sha256(serialized).hexdigest()
        assert digest == "5a04cc11c5c66b0a31288c84a4809ec172d69c9964533b56927d584f9d439399"

    def test_vector_negative_zero(self):
        """{"n": -0} normalizes to {"n": 0} → f3013f93..."""
        normalized = normalize_for_hashing({"n": -0.0})
        assert normalized["n"] == 0  # -0 normalized to integer 0
        serialized = canonical_serialize_jcs(normalized)
        assert serialized == b'{"n":0}'
        digest = hashlib.sha256(serialized).hexdigest()
        assert digest == "f3013f933b9fb80ab6d995e7ad9da36f683837ba1d81e950c943d40111eac2f0"

    def test_vector_unicode_nfc(self):
        """{"s": "Café"} → d4f21edc..."""
        import unicodedata

        # Ensure NFC form
        cafe = unicodedata.normalize("NFC", "Caf\u00e9")
        serialized = canonical_serialize_jcs(normalize_for_hashing({"s": cafe}))
        assert serialized == '{"s":"Café"}'.encode("utf-8")
        digest = hashlib.sha256(serialized).hexdigest()
        assert digest == "d4f21edc957c8d5f5c6ba620f820dabb8b4afc2398a7603cf49e875cf2a36269"

    def test_canonical_hash_helper(self):
        """canonical_hash() convenience function returns correct hex."""
        result = canonical_hash({"n": 0.1})
        assert result == "c20c34ed16c837e86b4dcdb33f98c274c9f7da1231f64302082d2cd50743f951"

    def test_sort_keys_determinism(self):
        """Object key order does not affect canonical hash."""
        h1 = canonical_hash({"b": 2, "a": 1})
        h2 = canonical_hash({"a": 1, "b": 2})
        assert h1 == h2

    def test_nan_rejected(self):
        with pytest.raises(ValueError, match="NaN"):
            normalize_for_hashing({"x": float("nan")})

    def test_infinity_rejected(self):
        with pytest.raises(ValueError, match="Infinity"):
            normalize_for_hashing({"x": float("inf")})

    def test_negative_infinity_rejected(self):
        with pytest.raises(ValueError, match="Infinity"):
            normalize_for_hashing({"x": float("-inf")})

    def test_nfc_normalization_applied_to_keys(self):
        """String keys are NFC-normalized (Section 11.0.4)."""
        import unicodedata

        # NFD decomposed 'é' = e + combining accent
        key_nfd = "cafe\u0301"  # NFD
        key_nfc = unicodedata.normalize("NFC", key_nfd)  # → "café"
        normalized = normalize_for_hashing({key_nfd: "value"})
        assert key_nfc in normalized

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported type"):
            normalize_for_hashing({"x": object()})


# =========================================================================== #
# CitationItem validation                                                       #
# =========================================================================== #


class TestCitationItem:
    def test_valid_citation_no_provenance(self):
        c = CitationItem(**_citation())
        assert c.rag_document_id == _RAG_DOC_ID
        assert c.score == 0.91
        assert c.quote is None

    def test_valid_citation_with_provenance(self):
        c = CitationItem(
            **_citation(),
            quote="Today I ran",
            char_start=0,
            char_end=12,
        )
        assert c.quote == "Today I ran"
        assert c.char_end == 12

    def test_invalid_rag_document_id(self):
        with pytest.raises(ValueError, match="rag_document_id must be 32-hex"):
            CitationItem(rag_document_id="not-hex", chunk_id="x#chunk:0", score=0.5)

    def test_invalid_chunk_id_format(self):
        with pytest.raises(ValueError, match="chunk_id must match"):
            CitationItem(
                rag_document_id=_RAG_DOC_ID,
                chunk_id=f"{_RAG_DOC_ID}:0",  # wrong separator
                score=0.5,
            )

    def test_chunk_id_prefix_mismatch(self):
        other_doc = "bbbbccdd11223344aabbccdd11223344"
        with pytest.raises(ValueError, match="chunk_id must start with"):
            CitationItem(
                rag_document_id=_RAG_DOC_ID,
                chunk_id=f"{other_doc}#chunk:0",
                score=0.5,
            )

    def test_provenance_partial_raises(self):
        """All-or-none: providing only quote should fail."""
        with pytest.raises(ValueError, match="all-or-none"):
            CitationItem(**_citation(), quote="hello")

    def test_char_end_not_gt_start_raises(self):
        with pytest.raises(ValueError, match="char_end must be > char_start"):
            CitationItem(**_citation(), quote="hi", char_start=5, char_end=5)

    def test_infinite_score_rejected(self):
        with pytest.raises(ValueError, match="finite"):
            CitationItem(
                rag_document_id=_RAG_DOC_ID,
                chunk_id=f"{_RAG_DOC_ID}#chunk:0",
                score=float("inf"),
            )

    def test_unknown_key_rejected(self):
        with pytest.raises(Exception):
            CitationItem(**_citation(), unexpected_key="value")


# =========================================================================== #
# Contract registry                                                             #
# =========================================================================== #


class TestContractRegistry:
    def test_all_six_contracts_registered(self):
        for step in (
            "categorization",
            "quest_generation",
            "insight_extraction",
            "voice_transcription",
            "report_generation",
            "personality_message_generation",
        ):
            cls = ContractRegistry.get(step)
            assert issubclass(cls, BaseAIContract)

    def test_get_unknown_step_raises(self):
        with pytest.raises(ValueError, match="No contract registered"):
            ContractRegistry.get("nonexistent_step")

    def test_validate_returns_instance(self):
        instance = ContractRegistry.validate("categorization", _base_categorization())
        assert isinstance(instance, CategorizationContract)

    def test_validate_wraps_error_in_contract_validation_error(self):
        bad = _base_categorization(contract_version=99)
        with pytest.raises(ContractValidationError) as exc_info:
            ContractRegistry.validate("categorization", bad)
        assert "categorization" in str(exc_info.value)

    def test_validate_json_valid(self):
        raw = json.dumps(_base_categorization())
        instance = ContractRegistry.validate_json("categorization", raw)
        assert isinstance(instance, CategorizationContract)

    def test_validate_json_duplicate_keys_rejected(self):
        """Section 11.0.4: duplicate object keys MUST be rejected."""
        raw = '{"contract_version":1,"contract_version":1,"skill_id":null,' \
              '"theme_ids":[],"tags":[],"signals":{"energy":50,"valence":50,"success":50},' \
              '"citations":[]}'
        with pytest.raises(ContractValidationError, match="Duplicate"):
            ContractRegistry.validate_json("categorization", raw)

    def test_validate_json_invalid_json(self):
        with pytest.raises(ContractValidationError, match="Invalid JSON"):
            ContractRegistry.validate_json("categorization", "{not valid json}")


# =========================================================================== #
# Categorization contract (v1) — Section 11.3.1                              #
# =========================================================================== #


class TestCategorizationContract:
    def test_valid_full(self):
        c = CategorizationContract(**_base_categorization())
        assert c.contract_version == 1
        assert c.skill_id == _SKILL_ID
        assert c.theme_ids == [_THEME_ID_1]
        assert c.tags == ["focus", "work"]
        assert c.signals.energy == 76

    def test_null_skill_id_allowed(self):
        c = CategorizationContract(**_base_categorization(skill_id=None))
        assert c.skill_id is None

    def test_wrong_contract_version_rejected(self):
        with pytest.raises(Exception):
            CategorizationContract(**_base_categorization(contract_version=2))

    def test_unknown_key_rejected(self):
        with pytest.raises(Exception):
            CategorizationContract(**_base_categorization(extra_field="bad"))

    def test_invalid_skill_id_format(self):
        with pytest.raises(ValueError, match="32-hex"):
            CategorizationContract(**_base_categorization(skill_id="not-hex"))

    def test_theme_ids_max_8(self):
        too_many = [f"{i:032x}" for i in range(9)]
        with pytest.raises(ValueError, match="max 8"):
            CategorizationContract(**_base_categorization(theme_ids=too_many))

    def test_duplicate_theme_id_rejected(self):
        with pytest.raises(ValueError, match="Duplicate theme_id"):
            CategorizationContract(
                **_base_categorization(theme_ids=[_THEME_ID_1, _THEME_ID_1])
            )

    def test_tags_max_12(self):
        too_many = [str(i) for i in range(13)]
        with pytest.raises(ValueError, match="max 12"):
            CategorizationContract(**_base_categorization(tags=too_many))

    def test_duplicate_tag_rejected_after_normalization(self):
        with pytest.raises(ValueError, match="Duplicate tag"):
            CategorizationContract(**_base_categorization(tags=["Work", "work"]))

    def test_tag_normalized_to_lowercase(self):
        c = CategorizationContract(**_base_categorization(tags=["FOCUS", "Work"]))
        assert c.tags == ["focus", "work"]

    def test_signals_out_of_range(self):
        with pytest.raises(Exception):
            CategorizationContract(
                **_base_categorization(signals={"energy": 101, "valence": 50, "success": 50})
            )

    def test_signals_unknown_key_rejected(self):
        with pytest.raises(Exception):
            CategorizationContract(
                **_base_categorization(
                    signals={"energy": 50, "valence": 50, "success": 50, "mood": 90}
                )
            )

    # Persistence mapping helpers
    def test_map_energy_level_round_half_up(self):
        c = CategorizationContract(**_base_categorization(signals={"energy": 76, "valence": 50, "success": 50}))
        assert c.map_energy_level() == 8  # 76/10 = 7.6 → 8

    def test_map_energy_level_clamp_min(self):
        c = CategorizationContract(**_base_categorization(signals={"energy": 0, "valence": 50, "success": 50}))
        assert c.map_energy_level() == 1  # 0/10=0, clamped to 1

    def test_map_energy_level_clamp_max(self):
        c = CategorizationContract(**_base_categorization(signals={"energy": 100, "valence": 50, "success": 50}))
        assert c.map_energy_level() == 10

    def test_map_success_quality(self):
        c = CategorizationContract(**_base_categorization(signals={"energy": 50, "valence": 50, "success": 70}))
        assert c.map_success_quality() == 7  # 70/10 = 7.0

    def test_map_sentiment_score(self):
        c = CategorizationContract(**_base_categorization(signals={"energy": 50, "valence": 58, "success": 50}))
        # (58-50)/50 = 0.16
        assert c.map_sentiment_score() == pytest.approx(0.16, abs=1e-6)

    def test_map_sentiment_score_neutral(self):
        c = CategorizationContract(**_base_categorization(signals={"energy": 50, "valence": 50, "success": 50}))
        assert c.map_sentiment_score() == 0.0

    def test_map_skills_themes_involved_with_skill(self):
        c = CategorizationContract(**_base_categorization())
        result = c.map_skills_themes_involved()
        assert result[0] == _SKILL_ID
        assert _THEME_ID_1 in result

    def test_map_skills_themes_involved_no_skill(self):
        c = CategorizationContract(
            **_base_categorization(skill_id=None, theme_ids=[_THEME_ID_1])
        )
        assert c.map_skills_themes_involved() == [_THEME_ID_1]

    def test_map_skills_themes_involved_empty(self):
        c = CategorizationContract(
            **_base_categorization(skill_id=None, theme_ids=[])
        )
        assert c.map_skills_themes_involved() == []

    def test_compute_hash_is_deterministic(self):
        c1 = CategorizationContract(**_base_categorization())
        c2 = CategorizationContract(**_base_categorization())
        assert c1.compute_hash() == c2.compute_hash()

    def test_with_valid_citation(self):
        c = CategorizationContract(**_base_categorization(citations=[_citation()]))
        assert len(c.citations) == 1

    def test_tag_length_too_long(self):
        long_tag = "a" * 33
        with pytest.raises(ValueError, match="1..32"):
            CategorizationContract(**_base_categorization(tags=[long_tag]))

    def test_tag_empty_string_rejected(self):
        with pytest.raises(ValueError, match="1..32"):
            CategorizationContract(**_base_categorization(tags=[""]))


# =========================================================================== #
# Quest generation contract (v3) — Section 11.3.2                            #
# =========================================================================== #


class TestQuestGenerationContract:
    def test_valid_empty(self):
        c = QuestGenerationContract(**_base_quest_generation())
        assert c.contract_version == 3
        assert c.new_quests == []
        assert c.progress_updates == []

    def test_wrong_contract_version(self):
        with pytest.raises(Exception):
            QuestGenerationContract(**_base_quest_generation(contract_version=1))

    def test_unknown_key_rejected(self):
        with pytest.raises(Exception):
            QuestGenerationContract(**_base_quest_generation(extra="bad"))

    def test_new_quest_item_valid(self):
        quest = {
            "quest_type": "instant",
            "completion_type": "one_time",
            "title": "Write 10 minutes of journal",
            "description": "Do a short focused journaling sprint.",
            "due_at_utc_ms": 0,
            "expires_at_utc_ms": None,
        }
        c = QuestGenerationContract(**_base_quest_generation(new_quests=[quest]))
        assert c.new_quests[0].quest_type == "instant"

    def test_new_quest_expiry_before_due_rejected(self):
        quest = {
            "quest_type": "instant",
            "completion_type": "one_time",
            "title": "Test quest",
            "description": "desc",
            "due_at_utc_ms": 1000,
            "expires_at_utc_ms": 500,  # before due_at
        }
        with pytest.raises(ValueError, match="expires_at_utc_ms"):
            QuestGenerationContract(**_base_quest_generation(new_quests=[quest]))

    def test_new_quests_max_12(self):
        quest_tmpl = {
            "quest_type": "instant",
            "completion_type": "one_time",
            "title": "Q",
            "description": "d",
            "due_at_utc_ms": 0,
        }
        too_many = [quest_tmpl] * 13
        with pytest.raises(Exception):  # pydantic max_length or custom validator
            QuestGenerationContract(**_base_quest_generation(new_quests=too_many))

    def test_progress_updates_max_50(self):
        update = {
            "update_kind": "one_time_mark",
            "quest_id": _QUEST_ID,
            "completed_at_utc_ms": 0,
        }
        too_many = [update] * 51
        with pytest.raises(Exception):  # pydantic max_length or custom validator
            QuestGenerationContract(**_base_quest_generation(progress_updates=too_many))

    def test_one_time_mark_update(self):
        update = {
            "update_kind": "one_time_mark",
            "quest_id": _QUEST_ID,
            "completed_at_utc_ms": 1234567890,
        }
        c = QuestGenerationContract(**_base_quest_generation(progress_updates=[update]))
        assert isinstance(c.progress_updates[0], OneTimeMarkUpdate)

    def test_cumulative_delta_update(self):
        update = {
            "update_kind": "cumulative_delta",
            "quest_id": _QUEST_ID,
            "delta": 5,
            "event_at_utc_ms": 0,
        }
        c = QuestGenerationContract(**_base_quest_generation(progress_updates=[update]))
        assert isinstance(c.progress_updates[0], CumulativeDeltaUpdate)

    def test_streak_event_update(self):
        for event in ("increment", "reset", "break"):
            update = {
                "update_kind": "streak_event",
                "quest_id": _QUEST_ID,
                "event": event,
                "event_at_utc_ms": 0,
            }
            c = QuestGenerationContract(
                **_base_quest_generation(progress_updates=[update])
            )
            assert isinstance(c.progress_updates[0], StreakEventUpdate)

    def test_recursive_occurrence_update(self):
        update = {
            "update_kind": "recursive_occurrence",
            "quest_id": _QUEST_ID,
            "occurrence_at_utc_ms": 0,
            "occurrence_key": "2026-02-23#entry:" + "2" * 32,
        }
        c = QuestGenerationContract(**_base_quest_generation(progress_updates=[update]))
        assert isinstance(c.progress_updates[0], RecursiveOccurrenceUpdate)

    def test_unknown_update_kind_rejected(self):
        update = {
            "update_kind": "unknown_kind",
            "quest_id": _QUEST_ID,
        }
        with pytest.raises(Exception):
            QuestGenerationContract(**_base_quest_generation(progress_updates=[update]))

    def test_invalid_delta_exceeds_100000(self):
        update = {
            "update_kind": "cumulative_delta",
            "quest_id": _QUEST_ID,
            "delta": 100001,
            "event_at_utc_ms": 0,
        }
        with pytest.raises(Exception):
            QuestGenerationContract(**_base_quest_generation(progress_updates=[update]))

    def test_wrong_progress_schema_version(self):
        with pytest.raises(Exception):
            QuestGenerationContract(
                **_base_quest_generation(progress_updates_schema_version=2)
            )

    def test_quest_title_too_long(self):
        quest = {
            "quest_type": "instant",
            "completion_type": "one_time",
            "title": "x" * 81,
            "description": "desc",
            "due_at_utc_ms": 0,
        }
        with pytest.raises(Exception):
            QuestGenerationContract(**_base_quest_generation(new_quests=[quest]))


# =========================================================================== #
# Insight extraction contract (v1) — Section 11.3.3                          #
# =========================================================================== #


class TestInsightExtractionContract:
    def test_valid_with_insights(self):
        c = InsightExtractionContract(**_base_insight_extraction())
        assert c.contract_version == 1
        assert len(c.insights) == 1
        assert c.insights[0].title == "You focus better after a walk"

    def test_empty_insights_allowed(self):
        c = InsightExtractionContract(**_base_insight_extraction(insights=[]))
        assert c.insights == []

    def test_max_10_insights(self):
        many = [{"title": f"T{i}", "body": "body"} for i in range(11)]
        with pytest.raises(Exception):
            InsightExtractionContract(**_base_insight_extraction(insights=many))

    def test_wrong_contract_version(self):
        with pytest.raises(Exception):
            InsightExtractionContract(**_base_insight_extraction(contract_version=2))

    def test_unknown_key_rejected(self):
        with pytest.raises(Exception):
            InsightExtractionContract(**_base_insight_extraction(bad_key="x"))

    def test_unknown_key_in_insight_item_rejected(self):
        insight = {"title": "T", "body": "B", "extra": "bad"}
        with pytest.raises(Exception):
            InsightExtractionContract(**_base_insight_extraction(insights=[insight]))

    def test_insight_title_too_long(self):
        insight = {"title": "x" * 121, "body": "B"}
        with pytest.raises(Exception):
            InsightExtractionContract(**_base_insight_extraction(insights=[insight]))

    def test_insight_body_too_long(self):
        insight = {"title": "T", "body": "x" * 801}
        with pytest.raises(Exception):
            InsightExtractionContract(**_base_insight_extraction(insights=[insight]))

    def test_ordering_preserved(self):
        insights = [
            {"title": f"Insight {i}", "body": f"Body {i}"}
            for i in range(5)
        ]
        c = InsightExtractionContract(**_base_insight_extraction(insights=insights))
        for i, insight in enumerate(c.insights):
            assert insight.title == f"Insight {i}"


# =========================================================================== #
# Voice transcription contract (v1) — Section 11.3.4                         #
# =========================================================================== #


class TestVoiceTranscriptionContract:
    def test_valid_no_segments(self):
        c = VoiceTranscriptionContract(**_base_voice_transcription())
        assert c.confidence_0_1 == 0.93
        assert c.language == "en"

    def test_language_normalized_to_lowercase(self):
        c = VoiceTranscriptionContract(**_base_voice_transcription(language="EN-US"))
        assert c.language == "en-us"

    def test_empty_transcript_allowed(self):
        c = VoiceTranscriptionContract(**_base_voice_transcription(transcript_text=""))
        assert c.transcript_text == ""

    def test_confidence_out_of_range(self):
        with pytest.raises(Exception):
            VoiceTranscriptionContract(**_base_voice_transcription(confidence_0_1=1.1))

    def test_wrong_contract_version(self):
        with pytest.raises(Exception):
            VoiceTranscriptionContract(**_base_voice_transcription(contract_version=2))

    def test_unknown_key_rejected(self):
        with pytest.raises(Exception):
            VoiceTranscriptionContract(**_base_voice_transcription(extra="bad"))

    def test_valid_with_segments(self):
        segments = [
            {"start_ms": 0, "end_ms": 1200, "text": "Today I felt focused"},
            {"start_ms": 1200, "end_ms": 2400, "text": "after lunch"},
        ]
        c = VoiceTranscriptionContract(
            **_base_voice_transcription(
                transcript_text="Today I felt focused after lunch",
                segments=segments,
            )
        )
        assert len(c.segments) == 2

    def test_segment_end_before_start_rejected(self):
        segment = {"start_ms": 1200, "end_ms": 600, "text": "bad segment"}
        with pytest.raises(ValueError, match="end_ms"):
            VoiceTranscriptionContract(**_base_voice_transcription(segments=[segment]))

    def test_segments_overlap_rejected(self):
        segments = [
            {"start_ms": 0, "end_ms": 1500, "text": "first"},
            {"start_ms": 1000, "end_ms": 2000, "text": "second"},  # overlap
        ]
        with pytest.raises(ValueError, match="overlap"):
            VoiceTranscriptionContract(
                **_base_voice_transcription(
                    transcript_text="first second",
                    segments=segments,
                )
            )

    def test_segments_not_sorted_rejected(self):
        segments = [
            {"start_ms": 1000, "end_ms": 2000, "text": "second"},
            {"start_ms": 0, "end_ms": 900, "text": "first"},
        ]
        with pytest.raises(ValueError, match="sorted"):
            VoiceTranscriptionContract(
                **_base_voice_transcription(
                    transcript_text="second first",
                    segments=segments,
                )
            )

    def test_segment_text_not_substring_rejected(self):
        segments = [
            {"start_ms": 0, "end_ms": 100, "text": "xyz not in transcript"}
        ]
        with pytest.raises(ValueError, match="substring"):
            VoiceTranscriptionContract(
                **_base_voice_transcription(
                    transcript_text="completely different",
                    segments=segments,
                )
            )

    def test_normalized_transcript_nfc_and_whitespace(self):
        c = VoiceTranscriptionContract(
            **_base_voice_transcription(
                transcript_text="  Hello   world  ",
            )
        )
        assert c.normalized_transcript() == "Hello world"

    def test_normalized_transcript_preserves_paragraph_breaks(self):
        c = VoiceTranscriptionContract(
            **_base_voice_transcription(
                transcript_text="Para one\n\n\nPara two",
            )
        )
        assert c.normalized_transcript() == "Para one\n\nPara two"

    def test_segment_unknown_key_rejected(self):
        segment = {"start_ms": 0, "end_ms": 100, "text": "hi", "extra_field": "bad"}
        with pytest.raises(Exception):
            VoiceTranscriptionContract(**_base_voice_transcription(segments=[segment]))


# =========================================================================== #
# Report generation contract (v1) — Section 11.3.5                           #
# =========================================================================== #


class TestReportGenerationContract:
    def test_valid(self):
        c = ReportGenerationContract(**_base_report_generation())
        assert c.contract_version == 1
        assert c.report_kind == "weekly"
        assert len(c.sections) == 1

    def test_all_report_kinds(self):
        for kind in ("daily", "weekly", "monthly"):
            c = ReportGenerationContract(**_base_report_generation(report_kind=kind))
            assert c.report_kind == kind

    def test_invalid_report_kind(self):
        with pytest.raises(Exception):
            ReportGenerationContract(**_base_report_generation(report_kind="quarterly"))

    def test_wrong_contract_version(self):
        with pytest.raises(Exception):
            ReportGenerationContract(**_base_report_generation(contract_version=2))

    def test_unknown_key_rejected(self):
        with pytest.raises(Exception):
            ReportGenerationContract(**_base_report_generation(bad_key="x"))

    def test_sections_max_12(self):
        sections = [{"title": f"S{i}", "bullets": []} for i in range(13)]
        with pytest.raises(Exception):
            ReportGenerationContract(**_base_report_generation(sections=sections))

    def test_empty_sections_allowed(self):
        c = ReportGenerationContract(**_base_report_generation(sections=[]))
        assert c.sections == []

    def test_section_unknown_key_rejected(self):
        section = {"title": "T", "bullets": [], "extra": "bad"}
        with pytest.raises(Exception):
            ReportGenerationContract(**_base_report_generation(sections=[section]))

    def test_bullet_too_long(self):
        section = {"title": "T", "bullets": ["x" * 161]}
        with pytest.raises(ValueError, match="1..160"):
            ReportGenerationContract(**_base_report_generation(sections=[section]))

    def test_bullets_max_12(self):
        section = {"title": "T", "bullets": [f"bullet {i}" for i in range(13)]}
        with pytest.raises(Exception):
            ReportGenerationContract(**_base_report_generation(sections=[section]))

    def test_summary_too_long(self):
        with pytest.raises(Exception):
            ReportGenerationContract(
                **_base_report_generation(summary="x" * 1201)
            )

    def test_section_order_preserved(self):
        sections = [{"title": f"Section {i}", "bullets": []} for i in range(5)]
        c = ReportGenerationContract(**_base_report_generation(sections=sections))
        for i, section in enumerate(c.sections):
            assert section.title == f"Section {i}"


# =========================================================================== #
# Personality message generation contract (v2) — Section 11.3.6              #
# =========================================================================== #


class TestPersonalityMessageGenerationContract:
    def test_valid_entry_ack(self):
        c = PersonalityMessageGenerationContract(**_base_personality_message())
        assert c.contract_version == 2
        assert c.message_type == "entry_ack"
        assert c.personality == "raphael"

    def test_all_personalities(self):
        for personality in ("raphael", "therapist", "observer"):
            c = PersonalityMessageGenerationContract(
                **_base_personality_message(personality=personality)
            )
            assert c.personality == personality

    def test_invalid_personality(self):
        with pytest.raises(Exception):
            PersonalityMessageGenerationContract(
                **_base_personality_message(personality="unknown_bot")
            )

    def test_wrong_contract_version(self):
        with pytest.raises(Exception):
            PersonalityMessageGenerationContract(
                **_base_personality_message(contract_version=1)
            )

    def test_unknown_key_rejected(self):
        with pytest.raises(Exception):
            PersonalityMessageGenerationContract(
                **_base_personality_message(bad_field="x")
            )

    def test_entry_ack_non_empty_context_data_rejected(self):
        with pytest.raises(ValueError, match="entry_ack"):
            PersonalityMessageGenerationContract(
                **_base_personality_message(
                    message_type="entry_ack",
                    context_data={"quest_ids": [_QUEST_ID]},
                )
            )

    def test_quest_complete_valid(self):
        c = PersonalityMessageGenerationContract(
            **_base_personality_message(
                message_type="quest_complete",
                context_data={"quest_ids": [_QUEST_ID]},
            )
        )
        assert c.message_type == "quest_complete"
        assert c.context_data["quest_ids"] == [_QUEST_ID]

    def test_quest_complete_empty_quest_ids_rejected(self):
        with pytest.raises(ValueError, match="1..25"):
            PersonalityMessageGenerationContract(
                **_base_personality_message(
                    message_type="quest_complete",
                    context_data={"quest_ids": []},
                )
            )

    def test_quest_complete_too_many_quest_ids(self):
        many = [f"{i:032x}" for i in range(26)]
        with pytest.raises(ValueError, match="1..25"):
            PersonalityMessageGenerationContract(
                **_base_personality_message(
                    message_type="quest_complete",
                    context_data={"quest_ids": many},
                )
            )

    def test_quest_complete_invalid_quest_id_format(self):
        with pytest.raises(ValueError, match="32-hex"):
            PersonalityMessageGenerationContract(
                **_base_personality_message(
                    message_type="quest_complete",
                    context_data={"quest_ids": ["not-a-valid-id"]},
                )
            )

    def test_quest_nudge_valid(self):
        c = PersonalityMessageGenerationContract(
            **_base_personality_message(
                message_type="quest_nudge",
                context_data={"quest_ids": [_QUEST_ID]},
            )
        )
        assert c.message_type == "quest_nudge"

    def test_report_summary_valid(self):
        for kind in ("daily", "weekly", "monthly"):
            c = PersonalityMessageGenerationContract(
                **_base_personality_message(
                    message_type="report_summary",
                    context_data={"report_kind": kind},
                )
            )
            assert c.context_data["report_kind"] == kind

    def test_report_summary_invalid_kind(self):
        with pytest.raises(ValueError, match="daily|weekly|monthly"):
            PersonalityMessageGenerationContract(
                **_base_personality_message(
                    message_type="report_summary",
                    context_data={"report_kind": "yearly"},
                )
            )

    def test_report_summary_unknown_key_in_context_data_rejected(self):
        with pytest.raises(ValueError, match="Unknown keys"):
            PersonalityMessageGenerationContract(
                **_base_personality_message(
                    message_type="report_summary",
                    context_data={"report_kind": "weekly", "extra": "bad"},
                )
            )

    def test_text_too_long(self):
        with pytest.raises(Exception):
            PersonalityMessageGenerationContract(
                **_base_personality_message(text="x" * 2001)
            )

    def test_text_empty_rejected(self):
        with pytest.raises(Exception):
            PersonalityMessageGenerationContract(
                **_base_personality_message(text="")
            )

    def test_compute_hash_deterministic_across_message_types(self):
        c1 = PersonalityMessageGenerationContract(**_base_personality_message())
        c2 = PersonalityMessageGenerationContract(**_base_personality_message())
        assert c1.compute_hash() == c2.compute_hash()

    def test_all_message_types_accepted(self):
        type_context = {
            "entry_ack": {},
            "quest_complete": {"quest_ids": [_QUEST_ID]},
            "quest_nudge": {"quest_ids": [_QUEST_ID]},
            "report_summary": {"report_kind": "weekly"},
        }
        for mt, ctx in type_context.items():
            c = PersonalityMessageGenerationContract(
                **_base_personality_message(message_type=mt, context_data=ctx)
            )
            assert c.message_type == mt


# =========================================================================== #
# BaseAIContract.compute_hash integration                                      #
# =========================================================================== #


class TestComputeHash:
    def test_hash_changes_when_content_changes(self):
        c1 = CategorizationContract(**_base_categorization(tags=["focus"]))
        c2 = CategorizationContract(**_base_categorization(tags=["work"]))
        assert c1.compute_hash() != c2.compute_hash()

    def test_hash_stable_across_instances(self):
        data = _base_categorization()
        c1 = CategorizationContract(**data)
        c2 = CategorizationContract(**data)
        assert c1.compute_hash() == c2.compute_hash()

    def test_hash_is_64_hex_chars(self):
        c = CategorizationContract(**_base_categorization())
        h = c.compute_hash()
        assert len(h) == 64
        assert all(ch in "0123456789abcdef" for ch in h)
