"""
Hot-reloadable YAML configuration loader with Pydantic validation.

This module provides a configuration system that:
- Loads game balance settings from YAML
- Validates configuration with Pydantic models
- Supports hot-reloading when file changes (every 5 minutes check)
- Provides dot-notation access to nested values

Usage:
    from app.core.config_loader import get_config

    config = get_config()

    # Get values with dot notation
    base_xp = config.get("xp.base_journal_xp")
    theme_scaling = config.get("levels.theme.scaling_factor")

    # Force reload
    config.reload()
"""
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.schemas.config import GameBalanceConfig
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

# Default config path relative to project root
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "game_balance.yaml"

# Hot-reload check interval in seconds (5 minutes)
RELOAD_CHECK_INTERVAL = 300


class ConfigLoader:
    """
    Hot-reloadable configuration loader with Pydantic validation.

    Loads configuration from a YAML file and validates it against
    Pydantic models. Supports automatic hot-reloading when the
    configuration file changes.
    """

    def __init__(self, config_path: str | Path = DEFAULT_CONFIG_PATH) -> None:
        """
        Initialize the config loader.

        Args:
            config_path: Path to the YAML configuration file
        """
        self._config_path = Path(config_path)
        self._config: GameBalanceConfig | None = None
        self._last_modified: float = 0.0
        self._last_check: float = 0.0

        # Initial load
        self.reload()

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.

        Args:
            key: Dot-separated path to the value (e.g., "xp.base_journal_xp")
            default: Default value if key not found

        Returns:
            The configuration value or default

        Examples:
            config.get("xp.base_journal_xp")  # 50
            config.get("levels.theme.scaling_factor")  # 1.15
            config.get("titles.effect_multipliers.S_rank")  # 1.50
        """
        # Check for hot-reload
        if self._should_reload():
            self.reload()

        if self._config is None:
            return default

        # Navigate through the nested structure
        parts = key.split(".")
        value: Any = self._config

        for part in parts:
            if hasattr(value, part):
                value = getattr(value, part)
            elif isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default

        return value

    def reload(self) -> None:
        """
        Force reload configuration from file.

        Reads the YAML file, validates it with Pydantic, and updates
        the internal configuration state.
        """
        try:
            if not self._config_path.exists():
                logger.warning(
                    "Config file not found, using defaults",
                    path=str(self._config_path),
                )
                self._config = GameBalanceConfig()
                return

            with open(self._config_path, encoding="utf-8") as f:
                config_dict = yaml.safe_load(f)

            if config_dict is None:
                config_dict = {}

            self._config = self._validate(config_dict)
            self._last_modified = self._config_path.stat().st_mtime
            self._last_check = time.time()

            logger.info(
                "Configuration loaded",
                path=str(self._config_path),
            )

        except yaml.YAMLError as e:
            logger.error(
                "Failed to parse YAML config",
                path=str(self._config_path),
                error=str(e),
            )
            if self._config is None:
                self._config = GameBalanceConfig()

        except ValidationError as e:
            logger.error(
                "Configuration validation failed",
                path=str(self._config_path),
                errors=e.errors(),
            )
            if self._config is None:
                self._config = GameBalanceConfig()

    def _should_reload(self) -> bool:
        """
        Check if the configuration file should be reloaded.

        Returns True if:
        - At least RELOAD_CHECK_INTERVAL seconds have passed since last check
        - The file's modification time has changed

        Returns:
            True if configuration should be reloaded
        """
        current_time = time.time()

        # Don't check too frequently
        if current_time - self._last_check < RELOAD_CHECK_INTERVAL:
            return False

        self._last_check = current_time

        # Check if file was modified
        if not self._config_path.exists():
            return False

        current_mtime = self._config_path.stat().st_mtime
        return current_mtime > self._last_modified

    def _validate(self, config_dict: dict[str, Any]) -> GameBalanceConfig:
        """
        Validate configuration dictionary with Pydantic.

        Args:
            config_dict: Raw configuration dictionary from YAML

        Returns:
            Validated GameBalanceConfig instance

        Raises:
            ValidationError: If configuration is invalid
        """
        return GameBalanceConfig(**config_dict)

    @property
    def config(self) -> GameBalanceConfig:
        """
        Get the current validated configuration.

        Returns:
            The current GameBalanceConfig instance
        """
        if self._should_reload():
            self.reload()

        if self._config is None:
            self._config = GameBalanceConfig()

        return self._config


# Global singleton instance
_config_loader_instance: ConfigLoader | None = None


def get_config() -> ConfigLoader:
    """
    Get the global ConfigLoader singleton.

    Returns:
        The global ConfigLoader instance
    """
    global _config_loader_instance
    if _config_loader_instance is None:
        _config_loader_instance = ConfigLoader()
    return _config_loader_instance
