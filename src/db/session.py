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
from typing import Generator, Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.base import Base  # noqa: F401 — re-exported for convenience

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "dev.yaml"
_DEFAULT_SQLITE = _REPO_ROOT / "data" / "db" / "rpg_life_tracker.db"


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
            import yaml  # optional dependency; gracefully absent in minimal envs

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
    Create all tables defined in Base.metadata.

    Intended for initial setup and automated tests. In production, use Alembic
    migrations instead. This function is idempotent (CREATE TABLE IF NOT EXISTS).
    """
    # Ensure the data directory exists for file-based SQLite
    if DATABASE_URL.startswith("sqlite") and ":memory:" not in DATABASE_URL:
        db_path_str = DATABASE_URL.replace("sqlite:///", "")
        Path(db_path_str).parent.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)


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
