"""
Database session manager for the RPG Life Tracker.

Responsibilities:
    - Load database configuration from config/dev.yaml (with env var overrides)
    - Build the SQLAlchemy engine for SQLite (dev/test) or PostgreSQL (prod)
    - Provide a session factory and a FastAPI-compatible get_db() dependency
    - Expose init_db() / drop_db() utilities

Priority order for database URL resolution:
    1. DATABASE_URL env var (highest — used in CI, Docker, prod)
    2. config/dev.yaml  database section
    3. Hardcoded SQLite fallback at data/db/rpg_life_tracker.db

Config file location:
    Default: <repo_root>/config/dev.yaml
    Override: CONFIG_PATH env var

SQLite notes:
    - File-based:   default pool + check_same_thread=False
    - In-memory:    StaticPool (single shared connection — correct for :memory:)
    - FK enforcement enabled via PRAGMA foreign_keys=ON on every connection

PostgreSQL notes:
    - pool_pre_ping=True  — validates connections before use (handles idle timeouts)
    - URL: postgresql://<user>:<password>@<host>:<port>/<database>
"""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterator

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.base import Base  # noqa: F401 — re-exported for convenience

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "dev.yaml"
_DEFAULT_SQLITE = _REPO_ROOT / "data" / "db" / "rpg_life_tracker.db"


def _ensure_sqlite_parent_dir(url: str) -> None:
    """Create parent directory for file-based SQLite URLs when needed."""
    if not url.startswith("sqlite"):
        return
    if ":memory:" in url or url == "sqlite://":
        return

    db_path_str = url.replace("sqlite:///", "")
    Path(db_path_str).parent.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def _load_db_url() -> str:
    """
    Resolve the database URL using the priority chain described in the module
    docstring. Returns a full SQLAlchemy URL string.
    """
    # 1. Explicit env var wins immediately
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    # 2. YAML config file
    config_path = Path(os.getenv("CONFIG_PATH", str(_DEFAULT_CONFIG)))
    if config_path.exists():
        try:
            import yaml  # type: ignore[import-untyped]  # optional dependency

            with config_path.open() as fh:
                cfg = yaml.safe_load(fh) or {}

            db_cfg = cfg.get("database", {})
            db_type = db_cfg.get("type", "sqlite")

            if db_type == "postgresql":
                pg = db_cfg.get("postgresql", {})
                user = pg.get("username", "postgres")
                password = pg.get("password", "")
                host = pg.get("host", "localhost")
                port = pg.get("port", 5432)
                name = pg.get("database", "rpg_life_tracker")
                return f"postgresql://{user}:{password}@{host}:{port}/{name}"

            # SQLite path (default branch)
            sqlite_path = db_cfg.get("sqlite", {}).get("path", "")
            if sqlite_path:
                # Resolve relative paths from repo root
                resolved = Path(sqlite_path)
                if not resolved.is_absolute():
                    resolved = _REPO_ROOT / resolved
                return f"sqlite:///{resolved}"

        except Exception:  # yaml missing, malformed file, etc. — fall through
            pass

    # 3. Hardcoded fallback
    return f"sqlite:///{_DEFAULT_SQLITE}"


DATABASE_URL: str = _load_db_url()
_ensure_sqlite_parent_dir(DATABASE_URL)


# ---------------------------------------------------------------------------
# SQLite FK pragma — fires on every new connection
# ---------------------------------------------------------------------------
@event.listens_for(Engine, "connect")
def _enforce_sqlite_fks(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    """Enable SQLite foreign-key enforcement (disabled by default in SQLite)."""
    # Only applies to SQLite; other backends silently ignore the PRAGMA
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:  # non-SQLite backends raise here; ignore
        pass


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------
def _build_engine(url: str) -> Engine:
    """
    Build a SQLAlchemy engine appropriate for the given URL.

    SQLite (file-based):
        - check_same_thread=False   — allows FastAPI's thread pool to reuse connections
        - Default connection pool

    SQLite (in-memory, ':memory:'):
        - StaticPool                — single shared connection; required so all
                                      threads see the same in-memory database
        - check_same_thread=False

    PostgreSQL:
        - pool_pre_ping=True        — tests connections before checkout to
                                      recover from idle-timeout disconnects
    """
    echo = os.getenv("SQL_ECHO", "false").lower() == "true"

    if url.startswith("sqlite"):
        is_memory = ":memory:" in url or url == "sqlite://"
        kwargs: dict = {
            "connect_args": {"check_same_thread": False},
            "echo": echo,
        }
        if is_memory:
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)

    # PostgreSQL (and any other dialect)
    return create_engine(url, pool_pre_ping=True, echo=echo)


engine: Engine = _build_engine(DATABASE_URL)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # avoids lazy-load errors after commit in async contexts
)


# ---------------------------------------------------------------------------
# FastAPI dependency  (generator — works with Depends())
# ---------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session.

    Commits on success, rolls back on any exception, and always closes the
    session in the finally block.

    Usage::

        @router.get("/users")
        def list_users(db: Session = Depends(get_db)):
            return db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Context-manager variant  (useful outside of FastAPI — scripts, tests, etc.)
# ---------------------------------------------------------------------------
@contextmanager
def db_session() -> Iterator[Session]:
    """
    Context manager that provides a transactional database session.

    Commits on success, rolls back on exception, always closes.

    Usage::

        with db_session() as db:
            db.add(User(...))
        # auto-committed and closed
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Schema utilities
# ---------------------------------------------------------------------------
def init_db() -> None:
    """
    Create all tables defined in Base.metadata for isolated test databases.

    Production startup must rely on Alembic migrations instead of implicit
    ``create_all`` bootstrap. This helper is retained for tests and one-off
    local scratch databases only.
    """
    # Ensure the data directory exists for file-based SQLite
    _ensure_sqlite_parent_dir(DATABASE_URL)

    Base.metadata.create_all(bind=engine)
    _create_sqlite_tenant_integrity_triggers()


def _ensure_sqlite_users_compat_columns() -> None:
    """Backfill legacy SQLite schemas missing newer ``users`` columns."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    preferences_default = (
        '{"realm":{"scope":{"visual":true,"naming":false,"messages":false,'
        '"llm":false},"ranks_wording":{"preset":"standard"}},'
        '"skill_hierarchy":{"default_blocked_preference":false}}'
    )

    with engine.begin() as conn:
        existing_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
        }

        if "default_blocked_preference" not in existing_columns:
            conn.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN default_blocked_preference BOOLEAN NOT NULL DEFAULT 0"
                )
            )

        if "user_preferences" not in existing_columns:
            conn.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN user_preferences TEXT NOT NULL "
                    f"DEFAULT '{preferences_default}'"
                )
            )


def _create_sqlite_tenant_integrity_triggers() -> None:
    """Install required SQLite tenant-integrity triggers for optional SET NULL FKs."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    trigger_sql = [
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_quest_user
        BEFORE INSERT ON personality_messages
        WHEN NEW.quest_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM quests WHERE id = NEW.quest_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.quest_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_quest_user_upd
        BEFORE UPDATE OF quest_id, user_id ON personality_messages
        WHEN NEW.quest_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM quests WHERE id = NEW.quest_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.quest_id must belong to same user')
            END;
        END;
        """,
    ]

    with engine.begin() as conn:
        for stmt in trigger_sql:
            conn.execute(text(stmt))


def drop_db() -> None:
    """
    Drop all tables defined in Base.metadata.

    **Test teardown only.** Never call this in production.
    """
    Base.metadata.drop_all(bind=engine)


def check_connection() -> bool:
    """
    Verify the database is reachable. Returns True on success, False otherwise.
    Useful for health-check endpoints.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_database_url() -> str:
    """Return the active SQLAlchemy database URL used by the canonical stack."""
    return DATABASE_URL


def get_head_schema_revision() -> str | None:
    """Return the Alembic head revision for the canonical ``src`` stack."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except Exception:
        return None

    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    script = ScriptDirectory.from_config(cfg)
    heads = sorted(script.get_heads())
    return ",".join(heads) if heads else None


def get_current_schema_revision() -> str | None:
    """Return the current DB Alembic revision, or ``None`` if unversioned."""
    try:
        with engine.connect() as conn:
            inspector = inspect(conn)
            if "alembic_version" not in inspector.get_table_names():
                return None

            rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
            revisions = sorted(
                row[0]
                for row in rows
                if row and isinstance(row[0], str) and row[0].strip()
            )
            return ",".join(revisions) if revisions else None
    except Exception:
        return None


def schema_status() -> dict[str, Any]:
    """Return connectivity and revision status for the canonical schema."""
    connected = check_connection()
    current_revision = get_current_schema_revision() if connected else None
    head_revision = get_head_schema_revision()
    return {
        "connected": connected,
        "current_revision": current_revision,
        "head_revision": head_revision,
        "ready": bool(
            connected
            and current_revision is not None
            and head_revision is not None
            and current_revision == head_revision
        ),
    }


def assert_schema_ready() -> None:
    """
    Fail fast when the DB is reachable but not migrated to the current head.

    The active ``src`` runtime must not bootstrap schema state via
    ``Base.metadata.create_all``.
    """
    status = schema_status()
    if not status["connected"]:
        raise RuntimeError("Database connection check failed.")

    current_revision = status["current_revision"]
    head_revision = status["head_revision"]

    if current_revision is None:
        raise RuntimeError(
            "Database schema is not initialized for the canonical src stack. "
            "Run `alembic upgrade head` before starting the API."
        )

    if head_revision is None:
        raise RuntimeError("Could not determine Alembic head revision.")

    if current_revision != head_revision:
        raise RuntimeError(
            "Database schema is behind the canonical src stack. "
            f"Current revision: {current_revision}. Head revision: {head_revision}. "
            "Run `alembic upgrade head` before starting the API."
        )
