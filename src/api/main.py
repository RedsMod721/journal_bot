"""
FastAPI application for RPG Life Tracker.

Run (development):
    uvicorn src.api.main:app --app-dir . --host 127.0.0.1 --port 8002 --reload

Run (production):
    uvicorn src.api.main:app --app-dir . --host 127.0.0.1 --port 8002 --workers 4
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import anomaly, balance, entries, forgiveness, harmony, jobs, journal, personality, quests, skills, themes, users
from src.db.session import assert_schema_ready, check_connection, get_db, schema_status

try:
    from src.jobs.scheduler import init_scheduler, shutdown_scheduler
except Exception:  # pragma: no cover - optional runtime dependency
    def init_scheduler() -> None:
        logger.warning("Scheduler unavailable; APScheduler dependency not installed.")

    def shutdown_scheduler() -> None:
        return None

logger = logging.getLogger(__name__)
_DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "dev.yaml"
_DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
]


def _load_allowed_origins() -> list[str]:
    """Resolve CORS origins from env, config, or safe local-development defaults."""
    env_origins = os.getenv("CORS_ALLOW_ORIGINS")
    if env_origins is not None:
        parsed = [item.strip() for item in env_origins.split(",") if item.strip()]
        return parsed or list(_DEFAULT_CORS_ORIGINS)

    config_path = Path(os.getenv("CONFIG_PATH", str(_DEFAULT_CONFIG)))
    if config_path.exists():
        try:
            import yaml  # type: ignore[import-untyped]

            with config_path.open(encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}

            origins = cfg.get("api", {}).get("cors_allow_origins")
            if isinstance(origins, list):
                parsed = [str(item).strip() for item in origins if str(item).strip()]
                if parsed:
                    return parsed
        except Exception:
            logger.warning("Could not load api.cors_allow_origins from %s", config_path)

    return list(_DEFAULT_CORS_ORIGINS)


def _using_dependency_overridden_db(app: FastAPI) -> bool:
    """
    Detect isolated tests that inject their own DB session via ``get_db``.

    Canonical runtime startup must validate the configured ``src`` database and
    may start the scheduler. Test suites often override ``get_db`` with an
    in-memory SQLite session built directly from metadata; those helpers are
    intentionally outside the Alembic-managed runtime path.
    """
    return get_db in app.dependency_overrides


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Manage startup and shutdown for the canonical ``src`` runtime."""
    logger.info("RPG Life Tracker API starting up.")
    scheduler_started = False

    if _using_dependency_overridden_db(app):
        logger.info(
            "Detected dependency-overridden DB session; skipping canonical "
            "schema startup checks and scheduler initialization."
        )
    else:
        db_ok = check_connection()
        if not db_ok:
            logger.warning("Database connection check failed at startup; running degraded.")
        else:
            assert_schema_ready()
            logger.info("Database connection OK and schema is at head.")
            init_scheduler()
            scheduler_started = True

    yield

    if scheduler_started:
        shutdown_scheduler()
    logger.info("RPG Life Tracker API shutting down.")


app = FastAPI(
    title="RPG Life Tracker API",
    description=(
        "Journal-based gamification system. "
        "Submit journal entries and track AI-powered XP, quests, and skill progression."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_load_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(entries.router, prefix="/api/v1")

for prefix in ("/api", "/api/v1"):
    app.include_router(users.router, prefix=prefix)
    app.include_router(skills.router, prefix=prefix)
    app.include_router(themes.router, prefix=prefix)
    app.include_router(quests.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(forgiveness.router, prefix=prefix)
    app.include_router(balance.router, prefix=prefix)
    app.include_router(harmony.router, prefix=prefix)
    app.include_router(anomaly.router, prefix=prefix)
    app.include_router(personality.router, prefix=prefix)

app.include_router(journal.browse_router, prefix="/api/v1")


@app.get("/health", tags=["system"], summary="API health check")
def health_check() -> dict[str, Any]:
    """
    Lightweight liveness probe.

    Returns ``healthy`` when the API process is running and can reach the
    canonical database at the current Alembic head revision. Degraded mode is
    reported when the DB is unreachable or behind, while the process itself is
    still alive.
    """
    schema = schema_status()
    status = "healthy" if schema["connected"] and schema["ready"] else "degraded"
    return {
        "status": status,
        "service": "RPG Life Tracker API",
        "database": "connected" if schema["connected"] else "unreachable",
        "schema_ready": schema["ready"],
        "schema_revision": schema["current_revision"],
        "schema_head": schema["head_revision"],
    }


@app.get("/", tags=["system"], include_in_schema=False)
def root() -> dict[str, str]:
    return {"message": "RPG Life Tracker API - see /docs for usage."}
