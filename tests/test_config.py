"""
Tests for application configuration.

These tests verify that configuration values are properly loaded
and have expected types.
"""
from pathlib import Path


def test_config_paths_are_pathlib_objects():
    """Configuration paths should be Path objects."""
    from app.config import BASE_DIR, DATA_DIR, VOICE_UPLOADS_DIR, BACKUPS_DIR

    assert isinstance(BASE_DIR, Path)
    assert isinstance(DATA_DIR, Path)
    assert isinstance(VOICE_UPLOADS_DIR, Path)
    assert isinstance(BACKUPS_DIR, Path)


def test_config_directories_exist():
    """Configuration directories should be created."""
    from app.config import DATA_DIR, VOICE_UPLOADS_DIR, BACKUPS_DIR

    assert DATA_DIR.exists()
    assert VOICE_UPLOADS_DIR.exists()
    assert BACKUPS_DIR.exists()


def test_config_database_url_format():
    """DATABASE_URL should be a valid SQLite URL."""
    from app.config import DATABASE_URL

    assert isinstance(DATABASE_URL, str)
    assert DATABASE_URL.startswith("sqlite:///")


def test_config_api_settings():
    """API settings should have expected values."""
    from app.config import API_VERSION, API_TITLE, API_DESCRIPTION

    assert isinstance(API_VERSION, str)
    assert API_VERSION == "0.1.0"
    assert isinstance(API_TITLE, str)
    assert API_TITLE == "Status Window API"
    assert isinstance(API_DESCRIPTION, str)


def test_config_cors_settings():
    """CORS settings should be a list of allowed origins."""
    from app.config import ALLOWED_ORIGINS

    assert isinstance(ALLOWED_ORIGINS, list)
    assert len(ALLOWED_ORIGINS) > 0
    assert all(isinstance(origin, str) for origin in ALLOWED_ORIGINS)


def test_config_ollama_settings():
    """Ollama settings should have string values."""
    from app.config import OLLAMA_MODEL, OLLAMA_HOST

    assert isinstance(OLLAMA_MODEL, str)
    assert isinstance(OLLAMA_HOST, str)
    assert OLLAMA_HOST.startswith("http")


def test_config_whisper_settings():
    """Whisper settings should have valid values."""
    from app.config import WHISPER_MODEL_SIZE

    assert isinstance(WHISPER_MODEL_SIZE, str)
    assert WHISPER_MODEL_SIZE in ["tiny", "base", "small", "medium", "large"]


def test_config_debug_is_boolean():
    """DEBUG should be a boolean."""
    from app.config import DEBUG

    assert isinstance(DEBUG, bool)
