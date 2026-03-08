#!/usr/bin/env bash
set -euo pipefail

if [[ "${REQUIRE_AI_ENDPOINTS:-0}" == "1" ]]; then
  python scripts/validation/week3_preflight.py \
    --require-ai-endpoints \
    --require-runtime-deps \
    --require-seed-artifacts
else
  python scripts/validation/week3_preflight.py \
    --require-runtime-deps \
    --require-seed-artifacts
fi
python scripts/validation/validate_preseed_kb.py --strict-artifacts
python -m black --check src tests
python -m ruff check src tests
python -m mypy --explicit-package-bases src
python scripts/init_db.py --strict --expected-min-tables 52 --hide-tables
python scripts/validation/validate_canonical_schema.py
PYTHONPATH=. pytest --confcutdir=tests/unit tests/unit/ai/ tests/unit/db/ -q
if [[ "${RUN_SEEDED_RAG_TEST:-0}" == "1" ]]; then
  PYTHONPATH=. pytest --confcutdir=tests/unit tests/unit/ai/test_rag_seed_validation.py -q
fi
PYTHONPATH=. pytest --confcutdir=tests/test_performance tests/test_performance/test_week3_pipeline_smoke.py -q
