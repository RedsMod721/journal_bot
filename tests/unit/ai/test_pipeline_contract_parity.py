from __future__ import annotations

from dataclasses import asdict

from src.ai.pipeline.entry_pipeline import PipelineFailureResult, PipelineSuccessResult
from src.ai.pipeline_core import EntryProcessingFailureResult, EntryProcessingSuccessResult


def test_success_contract_parity_between_legacy_and_canonical_payloads() -> None:
    canonical_keys = set(asdict(PipelineSuccessResult()).keys())
    legacy_keys = set(asdict(EntryProcessingSuccessResult()).keys()) | {"quest_result"}

    required_shared_keys = {
        "entry_id",
        "user_id",
        "status",
        "processing_run_id",
        "job_id",
        "message",
        "message_id",
        "personality",
        "summary",
        "meta",
        "step_trace",
        "quality",
        "provenance",
        "insight_result",
        "personality_result",
        "quest_result",
    }

    assert required_shared_keys <= canonical_keys
    assert required_shared_keys <= legacy_keys


def test_failure_contract_parity_between_legacy_and_canonical_payloads() -> None:
    canonical_keys = set(asdict(PipelineFailureResult()).keys())
    legacy_keys = set(asdict(EntryProcessingFailureResult()).keys())

    required_shared_keys = {
        "entry_id",
        "user_id",
        "status",
        "processing_run_id",
        "job_id",
        "terminal_error",
        "noncritical_errors",
        "processing_duration_ms",
        "step_trace",
        "quality",
        "provenance",
    }

    assert required_shared_keys <= canonical_keys
    assert required_shared_keys <= legacy_keys
