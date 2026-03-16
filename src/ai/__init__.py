"""Week 3 AI integration package."""

from src.ai.cache import StepCache
from src.ai.ollama import OllamaClient
from src.ai.qdrant import QdrantClientAdapter
from src.ai.readiness import build_readiness_report

__all__ = [
    "OllamaClient",
    "QdrantClientAdapter",
    "PipelineProcessor",
    "StepCache",
    "build_readiness_report",
]


def __getattr__(name: str):
    if name == "PipelineProcessor":
        from src.ai.pipeline import PipelineProcessor

        return PipelineProcessor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
