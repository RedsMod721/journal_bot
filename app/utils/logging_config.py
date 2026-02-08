"""
Structured logging configuration for Status Window API.

This module provides:
- Structured logging with structlog
- JSON formatting for production logs
- Console output with colors for development
- Rotating file handler for persistent logs
- Execution time decorator for performance monitoring

Usage:
    from app.utils.logging_config import configure_logging, get_logger, log_execution_time

    # Configure logging at app startup
    configure_logging()

    # Get a logger for your module
    logger = get_logger(__name__)
    logger.info("User created", user_id="123", username="test")

    # Time function execution
    @log_execution_time
    def slow_function():
        ...
"""
import functools
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, TypeVar

import structlog
from pythonjsonlogger.json import JsonFormatter as jsonlogger

# Type variable for preserving function signatures in decorator
F = TypeVar("F", bound=Callable[..., Any])

# Log directory configuration
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"

# Ensure logs directory exists
LOG_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    """
    Configure structured logging for the application.

    Sets up:
    - Console handler with colorized output for development
    - Rotating file handler with JSON formatting for production
    - Log level from LOG_LEVEL environment variable (default: INFO)

    Should be called once at application startup.
    """
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Configure standard library logging
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler with colorized output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Rotating file handler with JSON formatting
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setLevel(log_level)
    json_formatter = jsonlogger(
        fmt="%(timestamp)s %(level)s %(name)s %(message)s",
        rename_fields={"levelname": "level", "asctime": "timestamp"},
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    file_handler.setFormatter(json_formatter)
    root_logger.addHandler(file_handler)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(module_name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger for a module.

    Args:
        module_name: The name of the module (typically __name__)

    Returns:
        A structured logger bound with the module name

    Usage:
        logger = get_logger(__name__)
        logger.info("Processing started", item_count=42)
    """
    return structlog.get_logger(module_name).bind(module=module_name)


def log_execution_time(func: F) -> F:
    """
    Decorator that logs function execution time.

    Only logs if execution takes longer than 10ms to avoid noise.

    Args:
        func: The function to wrap

    Returns:
        Wrapped function that logs execution time

    Usage:
        @log_execution_time
        def slow_function():
            time.sleep(0.1)
    """
    logger = get_logger(func.__module__)

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            if duration_ms > 10:
                logger.info(
                    f"{func.__name__} completed in {duration_ms:.2f}ms",
                    function_name=func.__name__,
                    duration_ms=round(duration_ms, 2),
                )

    return wrapper  # type: ignore[return-value]
