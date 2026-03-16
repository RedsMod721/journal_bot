"""Backward-compatible public facade for the legacy ``src.ai.pipeline`` module.

The original module lived at ``src/ai/pipeline.py`` and exposed the Week 3
pipeline runtime from ``src.ai.pipeline_core``. The package refactor keeps this
import path stable for existing route handlers, tests, and helper modules while
newer package internals evolve independently.
"""

from src.ai.cache import StepCache
from src.ai.ollama import OllamaClient
from src.ai.qdrant import QdrantClientAdapter
from src.ai.recovery import RecoveryQueue
from src.ai.pipeline_core import (
    JournalEntryPipeline,
    PIPELINE_VERSION,
    RULESET_VERSION,
    PipelineProcessor,
    PipelineStepError,
)

__all__ = [
    "JournalEntryPipeline",
    "OllamaClient",
    "PIPELINE_VERSION",
    "QdrantClientAdapter",
    "RecoveryQueue",
    "RULESET_VERSION",
    "PipelineProcessor",
    "PipelineStepError",
    "StepCache",
]
