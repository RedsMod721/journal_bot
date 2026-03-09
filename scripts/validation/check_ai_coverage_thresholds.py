"""Validate per-module coverage thresholds for critical AI modules.

Usage:
    python scripts/validation/check_ai_coverage_thresholds.py [coverage.json]

Exit codes:
    0 -> all thresholds satisfied
    1 -> missing report/module or threshold failure
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

THRESHOLDS = {
    "src/ai/cache.py": 95.0,
    "src/ai/ollama.py": 95.0,
    "src/ai/pipeline.py": 90.0,
    "src/ai/qdrant.py": 95.0,
    "src/ai/readiness.py": 90.0,
    "src/ai/runtime_config.py": 90.0,
}


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def main() -> int:
    report_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("coverage.json")
    if not report_path.exists():
        print(f"ERROR: Coverage report not found: {report_path}")
        return 1

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    files = payload.get("files", {})
    file_map = {_norm(path): meta for path, meta in files.items()}

    missing_modules = [module for module in THRESHOLDS if module not in file_map]
    if missing_modules:
        print("ERROR: Missing modules in coverage report:")
        for module in missing_modules:
            print(f"  - {module}")
        return 1

    failures: list[str] = []
    for module, minimum in THRESHOLDS.items():
        percent = float(file_map[module].get("summary", {}).get("percent_covered", 0.0))
        if percent < minimum:
            failures.append(f"{module}: {percent:.2f}% < {minimum:.2f}%")

    if failures:
        print("ERROR: AI module coverage thresholds failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("AI module coverage thresholds satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
