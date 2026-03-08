"""Readiness probe tests for Week 3 preflight contracts."""

from __future__ import annotations

from src.ai.readiness import (
    build_readiness_report,
    check_ollama_readiness,
    check_python_version,
    check_qdrant_readiness,
)
from src.db.base import Base
from src.db.session import engine
import src.db.models  # noqa: F401


class _HealthyOllama:
    def health(self):
        return {
            "connected": True,
            "model_available": True,
            "models": ["llama3.2:3b"],
        }


class _DownOllama:
    def health(self):
        raise RuntimeError("offline")


class _HealthyQdrant:
    collection = "rag_documents"
    vector_size = 8

    def ensure_collection(self):
        return None

    def search(self, _vector, limit=1):
        return []


class _DownQdrant:
    collection = "rag_documents"
    vector_size = 8

    def ensure_collection(self):
        raise RuntimeError("down")


def test_python_version_check_contract():
    result = check_python_version()
    assert "ok" in result
    assert "current" in result
    assert "required" in result


def test_ollama_readiness_contracts():
    assert check_ollama_readiness(_HealthyOllama())["ok"] is True
    down = check_ollama_readiness(_DownOllama())
    assert down["ok"] is False
    assert down["error"]


def test_qdrant_readiness_contracts():
    assert check_qdrant_readiness(_HealthyQdrant())["ok"] is True
    down = check_qdrant_readiness(_DownQdrant())
    assert down["ok"] is False
    assert down["error"]


def test_readiness_report_core_mode_ignores_external_ai_reachability():
    Base.metadata.create_all(bind=engine)
    report = build_readiness_report(require_ai_endpoints=False)
    assert "ok" in report
    assert "checks" in report
    assert "database" in report["checks"]
