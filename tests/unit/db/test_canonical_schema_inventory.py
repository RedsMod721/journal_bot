"""Canonical schema inventory tests."""

from sqlalchemy import inspect

from src.db.base import Base
from src.db.session import _create_sqlite_tenant_integrity_triggers, check_sqlite_trigger_integrity, engine
from scripts.validation.validate_canonical_schema import REQUIRED_INDEX_COLUMNS
import src.db.models  # noqa: F401


EXPECTED_TABLE_COUNT = 53


def test_base_metadata_contains_53_tables():
    assert len(Base.metadata.tables) == EXPECTED_TABLE_COUNT


def test_database_initialization_contains_53_tables():
    Base.metadata.create_all(bind=engine)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert len(tables) >= EXPECTED_TABLE_COUNT


def test_sqlite_trigger_integrity_includes_personality_and_quest_guards():
    Base.metadata.create_all(bind=engine)
    _create_sqlite_tenant_integrity_triggers()
    status = check_sqlite_trigger_integrity()
    assert status["ok"] is True


def test_canonical_control_plane_indexes_match_required_inventory():
    for table_name, required_indexes in REQUIRED_INDEX_COLUMNS.items():
        table = Base.metadata.tables[table_name]
        available = {
            index.name: tuple(column.name for column in index.columns)
            for index in table.indexes
        }
        for constraint in table.constraints:
            if getattr(constraint, "name", None):
                available[constraint.name] = tuple(
                    column.name for column in getattr(constraint, "columns", [])
                )

        for index_name, expected_columns in required_indexes.items():
            assert available.get(index_name) == expected_columns
