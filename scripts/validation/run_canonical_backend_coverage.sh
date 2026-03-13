#!/usr/bin/env bash
set -euo pipefail

pytest \
  tests/unit \
  tests/integration/test_anomaly_personality_api.py \
  tests/integration/test_entry_processing_api.py \
  tests/integration/test_forgiveness_api_endpoints.py \
  tests/integration/test_pipeline_e2e.py \
  tests/integration/test_week4_api_endpoints.py \
  tests/integration/test_week5_api_endpoints.py \
  --ignore=tests/test_api \
  -q \
  -o addopts='--verbose --strict-markers' \
  --cov=src.ai.cache \
  --cov=src.ai.ollama \
  --cov=src.ai.pipeline \
  --cov=src.ai.qdrant \
  --cov=src.ai.readiness \
  --cov=src.ai.runtime_config \
  --cov=src.api.routes.entries \
  --cov=src.api.routes.anomaly \
  --cov=src.api.routes.personality \
  --cov-report=term-missing \
  --cov-report=json:coverage.json \
  --cov-fail-under=0

python scripts/validation/check_canonical_backend_coverage.py coverage.json
