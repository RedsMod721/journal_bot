"""Per-module AI coverage regression gate.

This test enforces minimum coverage for critical AI modules using
``coverage.json`` produced by pytest-cov.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def test_ai_module_coverage_thresholds() -> None:
    if os.getenv("ENFORCE_AI_MODULE_THRESHOLDS") != "1":
        pytest.skip(
            "Per-module AI coverage gate is opt-in; run with "
            "ENFORCE_AI_MODULE_THRESHOLDS=1 after coverage generation."
        )

    coverage_path = Path("coverage.json")
    assert coverage_path.exists(), "coverage.json not found; run tests with pytest-cov"

    payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    files = payload.get("files", {})

    thresholds = {
        "src/ai/cache.py": 95.0,
        "src/ai/ollama.py": 95.0,
        "src/ai/pipeline.py": 90.0,
        "src/ai/qdrant.py": 95.0,
        "src/ai/readiness.py": 90.0,
        "src/ai/runtime_config.py": 90.0,
    }

    file_map = {_norm(path): meta for path, meta in files.items()}
    missing = [path for path in thresholds if path not in file_map]
    assert not missing, f"Missing modules in coverage report: {missing}"

    failures: list[str] = []
    for module, minimum in thresholds.items():
        percent = float(file_map[module].get("summary", {}).get("percent_covered", 0.0))
        if percent < minimum:
            failures.append(f"{module}: {percent:.2f}% < {minimum:.2f}%")

    assert not failures, "AI module coverage thresholds failed:\n" + "\n".join(failures)
