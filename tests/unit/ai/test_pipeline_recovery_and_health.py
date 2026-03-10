"""Coverage tests for pipeline recovery and health utilities."""

from __future__ import annotations

# ruff: noqa: E402

import logging
import sys
import types

import pytest

_stub = types.ModuleType("sentence_transformers")
_stub.SentenceTransformer = object  # type: ignore[attr-defined]
sys.modules.setdefault("sentence_transformers", _stub)

from src.ai.pipeline import (
    JournalEntryPipeline,
    PIPELINE_VERSION,
    PipelineProcessor,
)  # noqa: E402


class _OllamaHealthy:
    def health(self):
        return {"connected": True, "model_available": True}


class _OllamaDown:
    def health(self):
        return {"connected": False, "model_available": False}


class _RecoveryRecorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def save_failed_entry(self, **kwargs) -> None:
        self.calls.append(kwargs)


class _RecoveryBoom:
    def save_failed_entry(self, **_kwargs) -> None:
        raise RuntimeError("queue down")


class _QdrantOk:
    def ensure_collection(self) -> None:
        return None


def test_save_to_recovery_no_queue_logs_critical(
    caplog: pytest.LogCaptureFixture,
) -> None:
    processor = PipelineProcessor(
        db=object(),
        ollama=_OllamaHealthy(),
        qdrant=object(),
        recovery=None,
    )

    with caplog.at_level(logging.CRITICAL):
        processor._save_to_recovery(
            entry_id="e1",
            user_id="u1",
            idempotency_key="k1",
            error="boom",
            error_code="E1",
        )

    assert "no recovery_queue configured" in caplog.text


def test_save_to_recovery_calls_queue_with_pipeline_version() -> None:
    recovery = _RecoveryRecorder()
    processor = PipelineProcessor(
        db=object(),
        ollama=_OllamaHealthy(),
        qdrant=object(),
        recovery=recovery,
    )

    processor._save_to_recovery(
        entry_id="e2",
        user_id="u2",
        idempotency_key="k2",
        error="boom2",
        error_code="E2",
    )

    assert len(recovery.calls) == 1
    assert recovery.calls[0]["pipeline_version"] == PIPELINE_VERSION
    assert recovery.calls[0]["error_code"] == "E2"


def test_save_to_recovery_queue_failure_is_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    processor = PipelineProcessor(
        db=object(),
        ollama=_OllamaHealthy(),
        qdrant=object(),
        recovery=_RecoveryBoom(),
    )

    with caplog.at_level(logging.CRITICAL):
        processor._save_to_recovery(
            entry_id="e3",
            user_id="u3",
            idempotency_key="k3",
            error="boom3",
            error_code="E3",
        )

    assert "recovery_queue write also failed" in caplog.text


@pytest.mark.asyncio
async def test_check_services_health_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Adapter:
        def ensure_collection(self) -> None:
            return None

    monkeypatch.setattr("src.ai.pipeline.QdrantClientAdapter", _Adapter)
    pipeline = JournalEntryPipeline(
        db_session=object(),
        ollama_client=_OllamaHealthy(),
        qdrant_client=_Adapter(),
        recovery=_RecoveryRecorder(),
    )

    health = await pipeline.check_services_health()
    assert health == {
        "ollama": True,
        "ollama_model": True,
        "qdrant": True,
        "degraded": False,
    }


@pytest.mark.asyncio
async def test_check_services_health_degraded_for_non_adapter_qdrant() -> None:
    pipeline = JournalEntryPipeline(
        db_session=object(),
        ollama_client=_OllamaDown(),
        qdrant_client=object(),
        recovery=_RecoveryRecorder(),
    )

    health = await pipeline.check_services_health()
    assert health["ollama"] is False
    assert health["qdrant"] is False
    assert health["degraded"] is True


def test_rule_based_activity_extraction_handles_duration_and_default() -> None:
    activities = JournalEntryPipeline._rule_based_activity_extraction(
        "I coded for 1.5 hours and later walked."
    )
    labels = {item["activity"]: item["duration_minutes"] for item in activities}
    assert labels["Coding"] == 90
    assert labels["Walking"] == 90

    defaults = JournalEntryPipeline._rule_based_activity_extraction("I studied today.")
    assert defaults[0]["activity"] == "Studying"
    assert defaults[0]["duration_minutes"] == 30


@pytest.mark.asyncio
async def test_process_entry_setup_exception_is_saved_to_recovery() -> None:
    recovery = _RecoveryRecorder()
    pipeline = JournalEntryPipeline(
        db_session=object(),
        ollama_client=_OllamaHealthy(),
        qdrant_client=object(),
        recovery=recovery,
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("setup failed")

    pipeline._processor.process_entry = _boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="setup failed"):
        await pipeline.process_entry("entry-1", "user-1", idempotency_key="idemp-1")

    assert len(recovery.calls) == 1
    assert recovery.calls[0]["entry_id"] == "entry-1"
    assert recovery.calls[0]["user_id"] == "user-1"
    assert recovery.calls[0]["idempotency_key"] == "idemp-1"
    assert recovery.calls[0]["error_code"] == "SETUP_EXCEPTION"
    assert recovery.calls[0]["pipeline_version"] == PIPELINE_VERSION


def test_pipeline_init_handles_recovery_queue_initialization_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise():
        raise RuntimeError("cannot create recovery dir")

    monkeypatch.setattr("src.ai.pipeline.RecoveryQueue", _raise)

    pipeline = JournalEntryPipeline(
        db_session=object(),
        ollama_client=_OllamaHealthy(),
        qdrant_client=object(),
        recovery=None,
    )

    assert pipeline._recovery is None
