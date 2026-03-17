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
import re
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


def _sqlite_fk_target(
    conn: Any,
    table_name: str,
    constrained_column: str,
) -> str | None:
    """Return the referred table name for a specific SQLite FK column."""
    rows = conn.execute(text(f"PRAGMA foreign_key_list({table_name})")).mappings()
    for row in rows:
        if row.get("from") == constrained_column:
            table = row.get("table")
            return str(table) if table else None
    return None


def _repair_sqlite_users_active_arc_fk_target() -> bool:
    """
    Repair legacy SQLite FK drift where users.active_arc_id points to
    story_arcs__legacy_mb84 instead of canonical story_arcs.

    Returns True when a repair was applied.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return False

    with engine.begin() as conn:
        inspector = inspect(conn)
        if "users" not in inspector.get_table_names():
            return False

        fk_target = _sqlite_fk_target(conn, "users", "active_arc_id")
        if fk_target in (None, "story_arcs"):
            return False
        if not fk_target.startswith("story_arcs__legacy_"):
            return False

        create_sql = conn.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type='table' AND name='users'"
            )
        ).scalar_one_or_none()
        if not isinstance(create_sql, str) or not create_sql.strip():
            return False

        users_indexes = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='users' AND sql IS NOT NULL"
                )
            ).fetchall()
            if row and row[0]
        ]
        users_triggers = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='trigger' AND tbl_name='users' AND sql IS NOT NULL"
                )
            ).fetchall()
            if row and row[0]
        ]

        temp_table = "users__fk_fix_active_arc"
        conn.execute(text(f'DROP TABLE IF EXISTS "{temp_table}"'))

        rewritten_sql = re.sub(
            r'(?is)^\s*CREATE\s+TABLE\s+(?:"users"|`users`|\[users\]|users)',
            f'CREATE TABLE "{temp_table}"',
            create_sql,
            count=1,
        )
        fk_pattern = re.compile(
            rf'(?i)REFERENCES\s+(?:"|`|\[)?{re.escape(fk_target)}(?:"|`|\])?'
        )
        if not fk_pattern.search(rewritten_sql):
            return False
        rewritten_sql = fk_pattern.sub('REFERENCES "story_arcs"', rewritten_sql)

        conn.execute(text("PRAGMA foreign_keys=OFF"))
        try:
            conn.execute(text(rewritten_sql))

            columns = [
                row[1]
                for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
                if row and len(row) > 1
            ]
            if not columns:
                conn.execute(text(f'DROP TABLE IF EXISTS "{temp_table}"'))
                return False

            quoted_columns = ", ".join(f'"{name}"' for name in columns)
            conn.execute(
                text(
                    f'INSERT INTO "{temp_table}" ({quoted_columns}) '
                    f'SELECT {quoted_columns} FROM "users"'
                )
            )
            conn.execute(text('DROP TABLE "users"'))
            conn.execute(text(f'ALTER TABLE "{temp_table}" RENAME TO "users"'))

            for statement in users_indexes:
                conn.execute(text(statement))
            for statement in users_triggers:
                conn.execute(text(statement))
        finally:
            conn.execute(text("PRAGMA foreign_keys=ON"))

        repaired_target = _sqlite_fk_target(conn, "users", "active_arc_id")
        return repaired_target == "story_arcs"


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
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_entry_user
        BEFORE INSERT ON personality_messages
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.entry_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_personality_messages_entry_user_upd
        BEFORE UPDATE OF entry_id, user_id ON personality_messages
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                THEN RAISE(ABORT, 'personality_messages.entry_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_quests_entry_user
        BEFORE INSERT ON quests
        WHEN NEW.entry_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                THEN RAISE(ABORT, 'quests.entry_id must belong to same user')
            END;
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_quests_entry_user_upd
        BEFORE UPDATE OF entry_id, user_id ON quests
        WHEN NEW.entry_id IS NOT NULL
        BEGIN
            SELECT CASE
                WHEN (SELECT user_id FROM journal_entries WHERE id = NEW.entry_id) != NEW.user_id
                THEN RAISE(ABORT, 'quests.entry_id must belong to same user')
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


def check_runtime_schema_integrity() -> dict[str, Any]:
    """Validate critical Week 7 runtime columns and indexes."""
    _repair_sqlite_users_active_arc_fk_target()

    required_columns = {
        "users": {"confidence_threshold_streak"},
        "story_arcs": {
            "event_name",
            "theme_ids",
            "xp_requirement_multiplier_bp",
            "xp_reward_multiplier_bp",
            "decay_rate_multiplier_bp",
            "duration_days",
            "created_at",
            "updated_at",
            "completed_at",
        },
        "arc_triggers": {
            "confidence_score",
            "trigger_data",
            "triggered_at",
        },
        "quest_progress": {
            "required_progress",
            "last_progress_local_date",
            "updated_at_utc_ms",
        },
        "quest_progress_contribution_days": {
            "quest_id",
            "contribution_local_date",
        },
        "quest_progress_contribution_entries": {
            "quest_id",
            "entry_id",
            "contribution_local_date",
        },
        "xp_awards": {
            "skill_weight_bp",
            "quest_matcher_version",
            "awarded_at_utc_ms",
        },
    }
    required_indexes = {
        "story_arcs": {
            "idx_story_arcs_user": ("user_id",),
            "idx_story_arcs_status": ("status",),
            "idx_story_arcs_active_unique": ("user_id",),
        },
        "arc_triggers": {
            "idx_arc_triggers_arc": ("arc_id",),
            "idx_arc_triggers_type": ("trigger_type",),
            "idx_arc_triggers_user": ("user_id",),
        },
        "quest_progress_contribution_days": {
            "uq_contribution_days_user_quest_date": (
                "user_id",
                "quest_id",
                "contribution_local_date",
            ),
            "idx_contribution_days_quest": ("quest_id",),
            "idx_contribution_days_date": ("contribution_local_date",),
        },
        "quest_progress_contribution_entries": {
            "uq_contribution_entries_user_quest_entry": (
                "user_id",
                "quest_id",
                "entry_id",
            ),
            "idx_contribution_entries_quest": ("quest_id",),
            "idx_contribution_entries_entry": ("entry_id",),
        },
        "quests": {
            "idx_quests_instant_unique": ("user_id", "entry_id"),
            "idx_quests_streak_active_unique": ("user_id", "semantic_key"),
            "idx_quests_template_instance_unique": (
                "user_id",
                "template_quest_type",
                "instance_key",
            ),
            "idx_quests_recursive_successor_unique": ("user_id", "successor_key"),
        },
    }
    required_sql_snippets = {
        "idx_story_arcs_active_unique": ("where status = 'active'",),
        "idx_quests_instant_unique": ("where quest_type = 'instant'",),
        "idx_quests_streak_active_unique": (
            "quest_type = 'longterm'",
            "completion_type = 'streak'",
            "status = 'active'",
        ),
        "idx_quests_template_instance_unique": (
            "quest_type = 'longterm'",
            "completion_type in ('cumulative', 'recursive')",
        ),
        "idx_quests_recursive_successor_unique": (
            "quest_type = 'longterm'",
            "completion_type = 'recursive'",
        ),
    }
    required_fk_tables = {
        "users": {
            ("active_arc_id",): "story_arcs",
            ("forgiveness_config_id",): "forgiveness_configs",
        },
        "arc_triggers": {
            ("user_id",): "users",
            ("arc_id",): "story_arcs",
        },
        "story_arcs": {
            ("user_id",): "users",
        },
    }

    def _normalize_sql(value: str | None) -> str:
        return " ".join((value or "").lower().split())

    with engine.connect() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        missing: list[str] = []

        for table_name, expected_columns in required_columns.items():
            if table_name not in tables:
                missing.append(f"{table_name}:missing_table")
                continue
            present_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name in sorted(expected_columns - present_columns):
                missing.append(f"{table_name}.{column_name}")

        for table_name, expected_indexes in required_indexes.items():
            if table_name not in tables:
                continue
            present_indexes = {
                index["name"]: tuple(index.get("column_names") or [])
                for index in inspector.get_indexes(table_name)
            }
            present_indexes.update(
                {
                    constraint["name"]: tuple(constraint.get("column_names") or [])
                    for constraint in inspector.get_unique_constraints(table_name)
                    if constraint.get("name")
                }
            )
            for index_name, expected_columns in expected_indexes.items():
                if present_indexes.get(index_name) != expected_columns:
                    missing.append(f"{table_name}.{index_name}")

        sql_rows = conn.execute(
            text(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type IN ('table','index') AND sql IS NOT NULL"
            )
        ).fetchall()
        object_sql = {row[0]: _normalize_sql(row[1]) for row in sql_rows}
        for object_name, snippets in required_sql_snippets.items():
            normalized = object_sql.get(object_name, "")
            for snippet in snippets:
                if _normalize_sql(snippet) not in normalized:
                    missing.append(f"{object_name}:sql")
                    break

        for table_name, expected_fks in required_fk_tables.items():
            if table_name not in tables:
                continue
            fk_rows = inspector.get_foreign_keys(table_name)
            available = {
                tuple(fk.get("constrained_columns") or []): fk.get("referred_table")
                for fk in fk_rows
            }
            for constrained_columns, referred_table in expected_fks.items():
                if available.get(constrained_columns) != referred_table:
                    missing.append(f"{table_name}.fk.{constrained_columns}->{referred_table}")

    return {"ok": not missing, "missing": missing}


def schema_status() -> dict[str, Any]:
    """Return connectivity and revision status for the canonical schema."""
    connected = check_connection()
    current_revision = get_current_schema_revision() if connected else None
    head_revision = get_head_schema_revision()
    trigger_integrity = check_sqlite_trigger_integrity() if connected else {
        "ok": False,
        "missing": ["database_unreachable"],
    }
    runtime_schema_integrity = check_runtime_schema_integrity() if connected else {
        "ok": False,
        "missing": ["database_unreachable"],
    }
    return {
        "connected": connected,
        "current_revision": current_revision,
        "head_revision": head_revision,
        "trigger_integrity": trigger_integrity,
        "runtime_schema_integrity": runtime_schema_integrity,
        "ready": bool(
            connected
            and current_revision is not None
            and head_revision is not None
            and current_revision == head_revision
            and trigger_integrity["ok"]
            and runtime_schema_integrity["ok"]
        ),
    }


def check_sqlite_trigger_integrity() -> dict[str, Any]:
    """Validate required SQLite tenant-integrity triggers for canonical runtime."""
    if not DATABASE_URL.startswith("sqlite"):
        return {"ok": True, "missing": []}

    required = {
        "trg_personality_messages_quest_user",
        "trg_personality_messages_quest_user_upd",
        "trg_personality_messages_entry_user",
        "trg_personality_messages_entry_user_upd",
        "trg_quests_entry_user",
        "trg_quests_entry_user_upd",
    }

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='trigger'")
        ).fetchall()

    present = {row[0] for row in rows}
    missing = sorted(required - present)
    return {"ok": not missing, "missing": missing}


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

    trigger_integrity = status.get("trigger_integrity", {"ok": True, "missing": []})
    if not trigger_integrity["ok"]:
        raise RuntimeError(
            "Database schema revision is current but required SQLite tenant-integrity "
            f"triggers are missing: {', '.join(trigger_integrity['missing'])}. "
            "Run `alembic upgrade head` or reinitialize the canonical schema."
        )

    runtime_schema_integrity = status.get(
        "runtime_schema_integrity", {"ok": True, "missing": []}
    )
    if not runtime_schema_integrity["ok"]:
        raise RuntimeError(
            "Database schema revision is current but runtime-critical columns or "
            "indexes are missing: "
            f"{', '.join(runtime_schema_integrity['missing'])}. "
            "Run `alembic upgrade head` or repair the canonical schema."
        )
