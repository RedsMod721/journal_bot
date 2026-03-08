"""Canonical schema inventory tests."""

from sqlalchemy import inspect

from src.db.base import Base
from src.db.session import engine
import src.db.models  # noqa: F401


EXPECTED_TABLE_COUNT = 52


def test_base_metadata_contains_52_tables():
    assert len(Base.metadata.tables) == EXPECTED_TABLE_COUNT


def test_database_initialization_contains_52_tables():
    Base.metadata.create_all(bind=engine)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert len(tables) >= EXPECTED_TABLE_COUNT
