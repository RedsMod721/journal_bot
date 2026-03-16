from __future__ import annotations

import importlib

from src.ai import pipeline as pipeline_facade
from src.ai import pipeline_core
from src.ai.cache import StepCache
from src.ai.ollama import OllamaClient
from src.ai.qdrant import QdrantClientAdapter
from src.ai.recovery import RecoveryQueue


def test_pipeline_package_restores_legacy_exports() -> None:
    assert pipeline_facade.JournalEntryPipeline is pipeline_core.JournalEntryPipeline
    assert pipeline_facade.OllamaClient is OllamaClient
    assert pipeline_facade.PipelineProcessor is pipeline_core.PipelineProcessor
    assert pipeline_facade.PipelineStepError is pipeline_core.PipelineStepError
    assert pipeline_facade.QdrantClientAdapter is QdrantClientAdapter
    assert pipeline_facade.RecoveryQueue is RecoveryQueue
    assert pipeline_facade.StepCache is StepCache
    assert pipeline_facade.PIPELINE_VERSION == pipeline_core.PIPELINE_VERSION
    assert pipeline_facade.RULESET_VERSION == pipeline_core.RULESET_VERSION


def test_api_main_import_smoke() -> None:
    module = importlib.import_module("src.api.main")

    assert hasattr(module, "app")
