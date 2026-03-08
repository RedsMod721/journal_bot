# Week 3 Go/No-Go Checklist (`src/` Canonical)

This checklist is the release review sheet for Week 3 AI integration on the canonical `src/` stack.

## Scope

- In scope: `src/` pipeline, DB contracts, Ollama/Qdrant integration, validation scripts.
- Out of scope (deferred): distributed trusted-node runtime flows.
- Seed execution is owned externally; this checklist includes where seed windows must occur.

## Seed Windows (mandatory)

1. Seed Window A: run after schema/migration validation and before first Week 3 end-to-end test.
2. Seed Window B: run after Qdrant is online and before retrieval-dependent tests.

### Seed Window A command bundle

```bash
python scripts/seeding/import_kb_master.py
python scripts/validation/validate_preseed_kb.py --strict-artifacts
```

### Seed Window B command bundle

```bash
python scripts/seeding/upload_seeded_rag_to_qdrant.py --expected-min-docs 1000
RUN_SEEDED_RAG_TEST=1 pytest --confcutdir=tests/unit tests/unit/ai/test_rag_seed_validation.py -q
```

Notes:
- The canonical local profile in `config/dev.yaml` uses `ai.qdrant.mode: local`, so no external Qdrant daemon is required for local Week 3 validation.
- For remote Qdrant service validation, set `QDRANT_MODE=remote` and provide host/port env vars.

## Pass/Fail Gates

### 1. Preflight

Command:

```bash
python scripts/validation/week3_preflight.py --require-runtime-deps --require-seed-artifacts
```

Pass if:
- `ok: true` for core checks (python/imports/tools/database/seed-contract)
- no missing canonical tables/triggers

Optional strict external gate:

```bash
python scripts/validation/week3_preflight.py --require-runtime-deps --require-seed-artifacts --require-ai-endpoints
```

Pass if:
- Ollama reachable and Qdrant reachable

### 2. Canonical schema gate

Commands:

```bash
python scripts/init_db.py --strict --expected-min-tables 52 --hide-tables
python scripts/validation/validate_canonical_schema.py
```

Pass if:
- DB initializes cleanly
- canonical validator reports no missing tables/triggers

### 3. Seed contract gate

Command:

```bash
python scripts/validation/validate_preseed_kb.py --strict-artifacts
```

Pass if:
- canonical KB seed files exist in `data/seeds/kb/`
- matcher artifacts exist with `schema_version = 1`
- strict artifact determinism check passes

### 4. Code quality gate

Commands:

```bash
python -m black --check src tests
python -m ruff check src tests
python -m mypy --explicit-package-bases src
```

Pass if all return exit code `0`.

### 5. Unit contract gate (pipeline/idempotency/outbox)

Command:

```bash
pytest --confcutdir=tests/unit tests/unit/ai/ tests/unit/db/ -q
```

Pass if:
- all tests pass
- replay/idempotency tests show no duplicate side effects
- degraded-mode tests pass for Ollama-down and Qdrant-down

### 6. Performance smoke gate

Command:

```bash
pytest --confcutdir=tests/test_performance tests/test_performance/test_week3_pipeline_smoke.py -q
```

Pass if:
- smoke test passes
- single local-stub pipeline run remains under 30s

### 7. End-to-end Week 3 gate (post seed window B)

Command (recommended bundle):

```bash
scripts/validation/run_validation_gates.sh
```

Strict external bundle:

```bash
REQUIRE_AI_ENDPOINTS=1 RUN_SEEDED_RAG_TEST=1 scripts/validation/run_validation_gates.sh
```

Pass if all stages pass with no skipped blocking gate.

## Go Decision

Declare **GO** only when:
1. Seed windows A and B were completed for the target environment.
2. All pass/fail gates above are green.
3. Healthy and degraded AI dependency paths both pass tests.
4. No idempotency/outbox duplicate-write regressions are observed.

Declare **NO-GO** when any blocking gate fails.
