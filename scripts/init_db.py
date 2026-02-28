"""
Database initialization script for the RPG Life Tracker.

Creates all tables defined in SQLAlchemy metadata and verifies the resulting
database schema. Intended for first-run setup and test environments.
"""
import argparse
import os
import sys
import logging
from pathlib import Path
from typing import Sequence

# Ensure repo root is importable when running: python scripts/init_db.py
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy import inspect

from src.db.base import Base
from src.db.session import engine, init_db

# Register ORM models with Base.metadata before init_db() / validation.
import src.db.models  # noqa: F401

DEFAULT_EXCLUDED_TABLES = {"alembic_version"}

try:
    from loguru import logger
except ImportError:
    class _StdLogger:
        def __init__(self) -> None:
            self._logger = logging.getLogger("init_db")

        def info(self, message: str, *args) -> None:
            self._logger.info(message.format(*args))

        def warning(self, message: str, *args) -> None:
            self._logger.warning(message.format(*args))

        def error(self, message: str, *args) -> None:
            self._logger.error(message.format(*args))

        def success(self, message: str, *args) -> None:
            self._logger.info(message.format(*args))

        def remove(self) -> None:
            pass

        def add(self, _sink, level: str = "INFO") -> None:
            logging.basicConfig(
                level=getattr(logging, level, logging.INFO),
                format="%(levelname)s: %(message)s",
            )

    logger = _StdLogger()


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize database tables and verify schema creation."
    )
    parser.add_argument(
        "--expected-min-tables",
        type=int,
        default=None,
        help="Fail if the final table count is below this number.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if model tables are missing from the database.",
    )
    parser.add_argument(
        "--hide-tables",
        action="store_true",
        help="Do not print the full table list.",
    )
    return parser.parse_args(argv)


def _configure_logger() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.remove()
    logger.add(sys.stderr, level=level)


def _verify_schema(table_names: set[str], expected_min_tables: int | None, strict: bool) -> bool:
    model_tables = set(Base.metadata.tables.keys())
    ignored_tables = DEFAULT_EXCLUDED_TABLES

    missing_tables = sorted(model_tables - table_names)
    unmanaged_tables = sorted(table_names - model_tables - ignored_tables)

    if expected_min_tables is not None and len(table_names) < expected_min_tables:
        logger.error(
            "Table count check failed: found {} table(s), expected at least {}.",
            len(table_names),
            expected_min_tables,
        )
        return False

    if missing_tables:
        logger.error(
            "Schema validation failed: {} model table(s) missing in DB: {}",
            len(missing_tables),
            ", ".join(missing_tables),
        )
        if strict:
            return False
        logger.warning("Continuing because --strict was not set.")

    if unmanaged_tables:
        logger.warning(
            "Found {} table(s) not present in model metadata: {}",
            len(unmanaged_tables),
            ", ".join(unmanaged_tables),
        )

    return True


def main(argv: Sequence[str] | None = None) -> int:
    """Initialize database tables and verify creation."""
    args = _parse_args(argv or sys.argv[1:])
    _configure_logger()

    logger.info("Initializing database...")
    logger.info("Database URL: {}", engine.url)
    init_db()

    inspector = inspect(engine)
    table_names = sorted(inspector.get_table_names())
    table_name_set = set(table_names)

    logger.success(
        "Database initialized successfully ({} table(s) found)",
        len(table_names),
    )
    if not args.hide_tables:
        logger.info("Tables: {}", ", ".join(table_names) if table_names else "<none>")

    is_valid = _verify_schema(
        table_names=table_name_set,
        expected_min_tables=args.expected_min_tables,
        strict=args.strict,
    )
    return 0 if is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
