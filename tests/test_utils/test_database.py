"""
Tests for database utility helpers.

These tests avoid touching the real database and only verify metadata helpers.
"""
from pathlib import Path

from app.utils.database import get_database_info


def test_get_database_info_keys_and_types():
    """get_database_info should return expected keys and types."""
    info = get_database_info()

    assert set(info.keys()) == {
        "database_url",
        "database_path",
        "database_exists",
        "directory_exists",
    }
    assert isinstance(info["database_url"], str)
    assert isinstance(info["database_path"], str)
    assert isinstance(info["database_exists"], bool)
    assert isinstance(info["directory_exists"], bool)


def test_get_database_info_flags_match_filesystem():
    """database_exists should match the filesystem state."""
    info = get_database_info()
    db_path = Path(info["database_path"])

    assert info["database_exists"] == db_path.exists()
    assert info["directory_exists"] == db_path.parent.exists()
