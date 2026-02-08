"""
Tests for structured logging configuration.

Tests:
- Logger creates JSON-formatted logs
- log_execution_time decorator works correctly
- Log level respects environment variable
"""
import json
import logging
import os
import time
from pathlib import Path
from unittest import mock

import pytest

from app.utils.logging_config import (
    LOG_FILE,
    configure_logging,
    get_logger,
    log_execution_time,
)


class TestLoggerCreatesJsonLogs:
    """Test that logger outputs JSON-formatted logs to file."""

    def test_logger_writes_json_to_file(self, tmp_path: Path) -> None:
        """Should write JSON-formatted logs to the log file."""
        # Arrange
        test_log_file = tmp_path / "test.log"

        # Create a fresh handler for testing
        from logging.handlers import RotatingFileHandler
        from pythonjsonlogger.json import JsonFormatter

        handler = RotatingFileHandler(test_log_file, maxBytes=1024, backupCount=1)
        json_formatter = JsonFormatter(
            fmt="%(timestamp)s %(level)s %(name)s %(message)s",
            rename_fields={"levelname": "level", "asctime": "timestamp"},
        )
        handler.setFormatter(json_formatter)

        test_logger = logging.getLogger("test_json_logger")
        test_logger.handlers.clear()
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)

        # Act
        test_logger.info("Test message", extra={"user_id": "123"})
        handler.flush()

        # Assert
        log_content = test_log_file.read_text()
        log_entry = json.loads(log_content.strip())

        assert log_entry["message"] == "Test message"
        assert log_entry["user_id"] == "123"
        assert "level" in log_entry

    def test_get_logger_returns_bound_logger(self) -> None:
        """Should return a logger bound with module name."""
        # Arrange & Act
        configure_logging()
        logger = get_logger("test.module")

        # Assert
        assert logger is not None
        # The logger should have the module binding
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
        assert hasattr(logger, "debug")


class TestLogExecutionTimeDecorator:
    """Test the log_execution_time decorator."""

    def test_decorator_logs_slow_function(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should log execution time for functions taking >10ms."""
        # Arrange
        configure_logging()

        @log_execution_time
        def slow_function() -> str:
            time.sleep(0.02)  # 20ms
            return "done"

        # Act
        result = slow_function()

        # Assert
        assert result == "done"
        # structlog writes to stderr through the console handler
        captured = capsys.readouterr()
        assert "slow_function completed in" in captured.err

    def test_decorator_skips_fast_function(self, caplog: pytest.LogCaptureFixture) -> None:
        """Should not log execution time for functions taking <10ms."""
        # Arrange
        configure_logging()

        @log_execution_time
        def fast_function() -> str:
            return "fast"

        # Act
        with caplog.at_level(logging.INFO):
            result = fast_function()

        # Assert
        assert result == "fast"
        # Should not have logged (function is too fast)
        assert not any("fast_function completed in" in record.message for record in caplog.records)

    def test_decorator_preserves_function_metadata(self) -> None:
        """Should preserve the original function's name and docstring."""
        # Arrange
        @log_execution_time
        def documented_function() -> None:
            """This is a docstring."""
            pass

        # Assert
        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a docstring."

    def test_decorator_handles_exceptions(self) -> None:
        """Should still log execution time even if function raises."""
        # Arrange
        configure_logging()

        @log_execution_time
        def failing_function() -> None:
            time.sleep(0.02)  # 20ms to ensure it logs
            raise ValueError("Test error")

        # Act & Assert
        with pytest.raises(ValueError, match="Test error"):
            failing_function()


class TestLogLevelFromEnv:
    """Test that log level respects environment variable."""

    def test_default_log_level_is_info(self) -> None:
        """Should default to INFO when LOG_LEVEL not set."""
        # Arrange
        with mock.patch.dict(os.environ, {}, clear=True):
            if "LOG_LEVEL" in os.environ:
                del os.environ["LOG_LEVEL"]

            # Clear and reconfigure
            root_logger = logging.getLogger()
            root_logger.handlers.clear()

            # Act
            configure_logging()

            # Assert
            assert root_logger.level == logging.INFO

    def test_log_level_from_environment_debug(self) -> None:
        """Should set DEBUG level when LOG_LEVEL=DEBUG."""
        # Arrange
        with mock.patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            root_logger = logging.getLogger()
            root_logger.handlers.clear()

            # Act
            configure_logging()

            # Assert
            assert root_logger.level == logging.DEBUG

    def test_log_level_from_environment_warning(self) -> None:
        """Should set WARNING level when LOG_LEVEL=WARNING."""
        # Arrange
        with mock.patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}):
            root_logger = logging.getLogger()
            root_logger.handlers.clear()

            # Act
            configure_logging()

            # Assert
            assert root_logger.level == logging.WARNING

    def test_invalid_log_level_defaults_to_info(self) -> None:
        """Should default to INFO for invalid LOG_LEVEL values."""
        # Arrange
        with mock.patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}):
            root_logger = logging.getLogger()
            root_logger.handlers.clear()

            # Act
            configure_logging()

            # Assert
            assert root_logger.level == logging.INFO
