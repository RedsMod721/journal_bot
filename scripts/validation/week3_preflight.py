"""Week 3 preflight checks (python, deps, DB schema, Ollama, Qdrant)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.ai.readiness import build_readiness_report_v2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-ai-endpoints",
        action="store_true",
        help="Fail if Ollama or Qdrant is unreachable.",
    )
    parser.add_argument(
        "--require-seed-artifacts",
        action="store_true",
        help="Fail if canonical seed files/artifacts are missing or hash contract mismatches.",
    )
    parser.add_argument(
        "--require-runtime-deps",
        action="store_true",
        help="Fail if required tooling dependencies (black/ruff/mypy/pytest) are missing.",
    )
    args = parser.parse_args()

    report = build_readiness_report_v2(
        require_ai_endpoints=args.require_ai_endpoints,
        require_seed_artifacts=args.require_seed_artifacts,
        require_runtime_deps=args.require_runtime_deps,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
