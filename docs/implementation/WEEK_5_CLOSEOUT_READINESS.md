# Week 5 Close-Out Readiness

This document is the canonical operator/developer flow for the hardened Week 5
baseline.

## Canonical runtime

- API entrypoint: `src.api.main:app`
- DB/session stack: `src.db.session`
- ORM metadata: `src.db.base.Base` + `import src.db.models`
- Schema authority: Alembic only
- Local backend port: `8002`
- Local frontend web/Tauri dev server port: `1420`

The API now fails fast when the configured canonical DB is reachable but not at
the current Alembic head revision. It does not call `Base.metadata.create_all()`
on startup.

## Local startup and cleanup

Canonical cleanup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_dev_ports.ps1
```

Legacy note: do not use port `8000` or `8001` for this repo's local backend
anymore. The standardized local backend port is `8002`.

Canonical backend start:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1
```

Canonical frontend start (web):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend.ps1 -Mode web
```

Canonical frontend start (desktop/Tauri):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend.ps1 -Mode tauri
```

All-in-one refresh:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\refresh_app_cache.ps1
```

## Fresh database flow

```powershell
$env:DATABASE_URL='sqlite:///c:/Users/vazqse01/journal_bot/.pytest_tmp/week5_fresh_validation.db'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe scripts/seeding/seed_harmony_profiles.py
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --app-dir . --host 127.0.0.1 --port 8002
```

## Legacy local/dev DB repair flow

Older local SQLite DBs may predate Alembic tracking entirely. For those DBs,
stamp the last pre-canonical legacy revision first, then upgrade normally.

```powershell
$env:DATABASE_URL='sqlite:///c:/Users/vazqse01/journal_bot/data/db/rpg_life_tracker.db'
.\.venv\Scripts\python.exe scripts/db/repair_legacy_alembic_state.py
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The repair script only stamps legacy DBs that already contain the old core
tables and have no existing `alembic_version` state.

## Demo seed flow

The Week 5 demo/profile seed is validated against migrated canonical schemas,
not against runtime `init_db()` bootstrap:

```powershell
$env:DATABASE_URL='sqlite:///c:/Users/vazqse01/journal_bot/.pytest_tmp/week5_fresh_validation.db'
.\.venv\Scripts\python.exe scripts/seeding/seed_harmony_profiles.py
```

## Validation commands

Backend Week 5 close-out subset:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_forgiveness_system.py `
  tests\test_week5_integration.py `
  tests\unit\core\test_balance_week5_services.py `
  tests\unit\core\test_forgiveness_week5_services.py `
  tests\unit\core\test_harmony_week5_services.py `
  tests\integration\test_forgiveness_api_endpoints.py `
  tests\integration\test_week4_api_endpoints.py `
  tests\integration\test_week5_api_endpoints.py `
  tests\integration\test_week5_migration_readiness.py `
  tests\unit\db\test_src_session.py `
  tests\unit\jobs\test_daily_decay_job.py `
  --no-cov -q
```

Frontend Week 5 close-out subset:

```powershell
cd rpg-life-ui
npm run test -- --run `
  src/services/forgiveness.service.test.ts `
  src/components/profile/ForgivenessProfileCard.test.tsx `
  src/components/settings/ForgivenessSettings.test.tsx `
  src/lib/forgiveness.test.ts
```

## Test collection policy

Default pytest collection now targets the canonical `src` stack. Legacy
`app/*` tests are skipped unless explicitly enabled:

```powershell
$env:INCLUDE_LEGACY_APP_TESTS='1'
.\.venv\Scripts\python.exe -m pytest
```
