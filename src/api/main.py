"""
FastAPI application for RPG Life Tracker.

Run (development):
    uvicorn src.api.main:app --reload --port 8000

Run (production):
    uvicorn src.api.main:app --workers 4 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import balance, forgiveness, harmony, jobs, journal, quests, skills, themes, users
from src.db.session import check_connection, init_db
from src.jobs.scheduler import init_scheduler, shutdown_scheduler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """
    Application lifespan handler.

    Startup:  ensure all DB tables exist (idempotent CREATE IF NOT EXISTS).
    Shutdown: log graceful teardown — connection pool cleanup is automatic.
    """
    logger.info("RPG Life Tracker API starting up.")
    init_db()

    db_ok = check_connection()
    if not db_ok:
        logger.warning(
            "Database connection check failed at startup — running degraded."
        )
    else:
        logger.info("Database connection OK.")

    init_scheduler()

    yield

    shutdown_scheduler()
    logger.info("RPG Life Tracker API shutting down.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


app = FastAPI(
    title="RPG Life Tracker API",
    description=(
        "Journal-based gamification system.  "
        "Submit journal entries and track AI-powered XP, quests, and skill progression."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict to UI origin(s) before production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

for prefix in ("/api", "/api/v1"):
    app.include_router(journal.router, prefix=prefix)
    app.include_router(users.router, prefix=prefix)
    app.include_router(skills.router, prefix=prefix)
    app.include_router(themes.router, prefix=prefix)
    app.include_router(quests.router, prefix=prefix)
    app.include_router(jobs.router, prefix=prefix)
    app.include_router(forgiveness.router, prefix=prefix)
    app.include_router(balance.router, prefix=prefix)
    app.include_router(harmony.router, prefix=prefix)

# ---------------------------------------------------------------------------
# System endpoints
# ---------------------------------------------------------------------------


@app.get("/health", tags=["system"], summary="API health check")
def health_check() -> dict[str, Any]:
    """
    Lightweight liveness probe.

    Returns ``healthy`` when the API process is running and can reach the
    database.  Degraded mode is reported when the DB is unreachable but the
    process itself is alive (pipeline will use RecoveryQueue in that case).
    """
    db_ok = check_connection()
    status = "healthy" if db_ok else "degraded"
    return {
        "status": status,
        "service": "RPG Life Tracker API",
        "database": "connected" if db_ok else "unreachable",
    }


@app.get("/", tags=["system"], include_in_schema=False)
def root() -> dict[str, str]:
    return {"message": "RPG Life Tracker API — see /docs for usage."}
