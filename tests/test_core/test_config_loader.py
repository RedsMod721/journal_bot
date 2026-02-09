"""
Tests for hot-reloadable YAML configuration loader.

Tests:
- Load config from YAML
- Get nested values with dot notation
- Hot reload on file change
- Validation catches invalid config
- get_config returns singleton
"""
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config_loader import ConfigLoader, get_config, RELOAD_CHECK_INTERVAL
from app.schemas.config import GameBalanceConfig


class TestLoadConfigFromYaml:
    """Test loading configuration from YAML files."""

    def test_load_config_from_yaml(self, tmp_path: Path) -> None:
        """Should load configuration from a valid YAML file."""
        # Arrange
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("""
xp:
  base_journal_xp: 75
  practice_time_multiplier: 0.8

levels:
  theme:
    base_xp: 150
    scaling_factor: 1.20
  skill:
    base_xp: 75
    scaling_factor: 1.25

titles:
  effect_multipliers:
    S_rank: 2.00
    A_rank: 1.50
    B_rank: 1.25
    C_rank: 1.15
    D_rank: 1.10
    E_rank: 1.05
    F_rank: 1.00

quests:
  daily_xp_reward: 150
  weekly_xp_reward: 750
  monthly_xp_reward: 3000

karma:
  lecture_listen_karma: 15
  good_deed_karma: 8
  negative_action_penalty: -5

items:
  knowledge_capsule_duration_days: 45
  consumable_effects_duration_minutes: 90
""")

        # Act
        loader = ConfigLoader(config_path=config_file)

        # Assert
        assert loader.config.xp.base_journal_xp == 75
        assert loader.config.xp.practice_time_multiplier == 0.8
        assert loader.config.levels.theme.base_xp == 150
        assert loader.config.levels.skill.scaling_factor == 1.25
        assert loader.config.titles.effect_multipliers.S_rank == 2.00
        assert loader.config.quests.daily_xp_reward == 150
        assert loader.config.karma.lecture_listen_karma == 15
        assert loader.config.items.knowledge_capsule_duration_days == 45

    def test_load_missing_file_uses_defaults(self, tmp_path: Path) -> None:
        """Should use default values when config file doesn't exist."""
        # Arrange
        missing_file = tmp_path / "missing.yaml"

        # Act
        loader = ConfigLoader(config_path=missing_file)

        # Assert - should have defaults
        assert loader.config.xp.base_journal_xp == 50
        assert loader.config.levels.theme.base_xp == 100

    def test_load_partial_config_fills_defaults(self, tmp_path: Path) -> None:
        """Should fill missing sections with defaults."""
        # Arrange
        config_file = tmp_path / "partial.yaml"
        config_file.write_text("""
xp:
  base_journal_xp: 100
""")

        # Act
        loader = ConfigLoader(config_path=config_file)

        # Assert
        assert loader.config.xp.base_journal_xp == 100  # From file
        assert loader.config.xp.practice_time_multiplier == 0.5  # Default
        assert loader.config.levels.theme.base_xp == 100  # Default

    def test_load_empty_file_uses_defaults(self, tmp_path: Path) -> None:
        """Should use defaults when YAML file is empty."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        loader = ConfigLoader(config_path=config_file)

        assert loader.config.xp.base_journal_xp == 50
        assert loader.config.levels.theme.base_xp == 100

    def test_load_with_extra_keys_ignores_unknown(self, tmp_path: Path) -> None:
        """Should ignore unknown keys in config file."""
        config_file = tmp_path / "extra.yaml"
        config_file.write_text("""
xp:
  base_journal_xp: 70
extra_section:
  some_key: 123
""")

        loader = ConfigLoader(config_path=config_file)

        assert loader.config.xp.base_journal_xp == 70

    def test_null_section_uses_defaults(self, tmp_path: Path) -> None:
        """Should fall back to defaults when section is null."""
        config_file = tmp_path / "null_section.yaml"
        config_file.write_text("""
xp: null
""")

        loader = ConfigLoader(config_path=config_file)

        assert loader.config.xp.base_journal_xp == 50


class TestGetNestedValueWithDotNotation:
    """Test dot notation access to nested values."""

    def test_get_nested_value_with_dot_notation(self, tmp_path: Path) -> None:
        """Should retrieve nested values using dot notation."""
        # Arrange
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
xp:
  base_journal_xp: 50
  practice_time_multiplier: 0.5

levels:
  theme:
    base_xp: 100
    scaling_factor: 1.15
  skill:
    base_xp: 50
    scaling_factor: 1.20

titles:
  effect_multipliers:
    S_rank: 1.50
    A_rank: 1.30
""")
        loader = ConfigLoader(config_path=config_file)

        # Act & Assert
        assert loader.get("xp.base_journal_xp") == 50
        assert loader.get("xp.practice_time_multiplier") == 0.5
        assert loader.get("levels.theme.base_xp") == 100
        assert loader.get("levels.theme.scaling_factor") == 1.15
        assert loader.get("levels.skill.base_xp") == 50
        assert loader.get("titles.effect_multipliers.S_rank") == 1.50
        assert loader.get("titles.effect_multipliers.A_rank") == 1.30

    def test_get_with_invalid_key_returns_default(self, tmp_path: Path) -> None:
        """Should return default value for non-existent keys."""
        # Arrange
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 50")
        loader = ConfigLoader(config_path=config_file)

        # Act & Assert
        assert loader.get("nonexistent.key") is None
        assert loader.get("nonexistent.key", default=42) == 42
        assert loader.get("xp.nonexistent", default="fallback") == "fallback"

    def test_get_with_invalid_intermediate_returns_default(self, tmp_path: Path) -> None:
        """Should return default when intermediate key is missing."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 50")
        loader = ConfigLoader(config_path=config_file)

        assert loader.get("xp.missing.child", default="none") == "none"

    def test_get_with_empty_key_returns_default(self, tmp_path: Path) -> None:
        """Should return default for empty key."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 50")
        loader = ConfigLoader(config_path=config_file)

        assert loader.get("", default="empty") == "empty"

    def test_get_top_level_section(self, tmp_path: Path) -> None:
        """Should retrieve entire sections."""
        # Arrange
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
xp:
  base_journal_xp: 50
  practice_time_multiplier: 0.5
""")
        loader = ConfigLoader(config_path=config_file)

        # Act
        xp_section = loader.get("xp")

        # Assert
        assert xp_section.base_journal_xp == 50
        assert xp_section.practice_time_multiplier == 0.5

    def test_get_returns_default_when_config_none(self, tmp_path: Path) -> None:
        """Should return default when internal config is None."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 50")

        loader = ConfigLoader(config_path=config_file)
        loader._config = None

        assert loader.get("xp.base_journal_xp", default=99) == 99

    def test_get_reads_dict_values(self, tmp_path: Path) -> None:
        """Should read dict-backed values when config is a dict."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 50")

        loader = ConfigLoader(config_path=config_file)
        loader._config = {"section": {"value": 123}}

        assert loader.get("section.value") == 123


class TestHotReloadOnFileChange:
    """Test automatic configuration reload when file changes."""

    def test_hot_reload_on_file_change(self, tmp_path: Path) -> None:
        """Should reload config when file is modified after check interval."""
        # Arrange
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 50")

        loader = ConfigLoader(config_path=config_file)
        assert loader.get("xp.base_journal_xp") == 50

        # Modify the file
        config_file.write_text("xp:\n  base_journal_xp: 999")

        # Simulate time passing by manipulating internal state
        # Set last_check to long ago so interval check passes
        loader._last_check = time.time() - RELOAD_CHECK_INTERVAL - 1
        # Set last_modified to 0 so file appears changed
        loader._last_modified = 0

        # Act - get should trigger reload
        value = loader.get("xp.base_journal_xp")

        # Assert
        assert value == 999

    def test_no_reload_within_interval(self, tmp_path: Path) -> None:
        """Should not reload if check interval hasn't passed."""
        # Arrange
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 50")

        loader = ConfigLoader(config_path=config_file)
        original_mtime = loader._last_modified

        # Modify file
        config_file.write_text("xp:\n  base_journal_xp: 999")

        # Act - don't manipulate time, interval hasn't passed
        value = loader.get("xp.base_journal_xp")

        # Assert - should still have old value because check interval hasn't passed
        assert value == 50
        assert loader._last_modified == original_mtime

    def test_force_reload(self, tmp_path: Path) -> None:
        """Should reload immediately when reload() is called explicitly."""
        # Arrange
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 50")

        loader = ConfigLoader(config_path=config_file)
        assert loader.get("xp.base_journal_xp") == 50

        # Modify file
        config_file.write_text("xp:\n  base_journal_xp: 777")

        # Act - force reload
        loader.reload()

        # Assert
        assert loader.get("xp.base_journal_xp") == 777

    def test_reload_after_file_deleted_uses_defaults(self, tmp_path: Path) -> None:
        """Should fall back to defaults if file is deleted and reload is forced."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 80")

        loader = ConfigLoader(config_path=config_file)
        assert loader.get("xp.base_journal_xp") == 80

        config_file.unlink()

        loader.reload()

        assert loader.config.xp.base_journal_xp == 50

    def test_config_property_initializes_default_when_missing(self, tmp_path: Path) -> None:
        """config property should initialize defaults when config is None."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 50")

        loader = ConfigLoader(config_path=config_file)
        loader._config = None

        assert loader.config.xp.base_journal_xp == 50


class TestValidationCatchesInvalidConfig:
    """Test Pydantic validation of configuration."""

    def test_validation_catches_invalid_config(self, tmp_path: Path) -> None:
        """Should reject invalid configuration values."""
        # Arrange
        config_file = tmp_path / "invalid.yaml"
        config_file.write_text("""
xp:
  base_journal_xp: -100
  practice_time_multiplier: 0.5
""")

        # Act - should use defaults on validation error
        loader = ConfigLoader(config_path=config_file)

        # Assert - should fall back to defaults
        assert loader.config.xp.base_journal_xp == 50  # Default, not -100

    def test_validation_rejects_wrong_types(self, tmp_path: Path) -> None:
        """Should reject wrong data types."""
        # Arrange
        config_file = tmp_path / "wrong_types.yaml"
        config_file.write_text("""
xp:
  base_journal_xp: "not a number"
""")

        # Act
        loader = ConfigLoader(config_path=config_file)

        # Assert - should fall back to defaults
        assert loader.config.xp.base_journal_xp == 50

    def test_invalid_yaml_syntax_uses_defaults(self, tmp_path: Path) -> None:
        """Should use defaults when YAML syntax is invalid."""
        # Arrange
        config_file = tmp_path / "bad_yaml.yaml"
        config_file.write_text("this: is: not: valid: yaml: {{{}}")

        # Act
        loader = ConfigLoader(config_path=config_file)

        # Assert - should use defaults
        assert loader.config.xp.base_journal_xp == 50

    def test_reload_invalid_config_keeps_last_good(self, tmp_path: Path) -> None:
        """Should keep last valid config when reload hits validation error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 60")

        loader = ConfigLoader(config_path=config_file)
        assert loader.config.xp.base_journal_xp == 60

        config_file.write_text("xp:\n  base_journal_xp: -1")

        loader.reload()

        assert loader.config.xp.base_journal_xp == 60

    def test_validation_accepts_boundary_values(self) -> None:
        """Should accept boundary values within schema constraints."""
        valid_data = {
          "xp": {"base_journal_xp": 1, "practice_time_multiplier": 10.0},
          "levels": {"theme": {"base_xp": 1, "scaling_factor": 3.0}},
          "quests": {
            "daily_xp_reward": 0,
            "weekly_xp_reward": 0,
            "monthly_xp_reward": 0,
          },
          "karma": {"negative_action_penalty": 0},
          "items": {
            "knowledge_capsule_duration_days": 1,
            "consumable_effects_duration_minutes": 1,
          },
        }

        config = GameBalanceConfig(**valid_data)

        assert config.xp.base_journal_xp == 1
        assert config.xp.practice_time_multiplier == 10.0
        assert config.levels.theme.scaling_factor == 3.0

    def test_validation_with_pydantic_directly(self) -> None:
        """Pydantic should raise ValidationError for invalid data."""
        # Arrange
        invalid_data = {
            "xp": {
                "base_journal_xp": -100,  # Must be >= 1
            }
        }

        # Act & Assert
        with pytest.raises(ValidationError):
            GameBalanceConfig(**invalid_data)


class TestGetConfigReturnsSingleton:
    """Test singleton behavior of get_config."""

    def test_get_config_returns_singleton(self) -> None:
        """Should return the same instance on multiple calls."""
        # Act
        config1 = get_config()
        config2 = get_config()

        # Assert
        assert config1 is config2

    def test_singleton_preserves_state(self) -> None:
        """State changes should persist across get_config calls."""
        # Arrange
        config1 = get_config()
        original_check_time = config1._last_check

        # Act
        config2 = get_config()

        # Assert
        assert config2._last_check == original_check_time

    def test_config_loader_instances_are_independent(self, tmp_path: Path) -> None:
        """New ConfigLoader instances should be independent."""
        # Arrange
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 123")

        # Act
        loader1 = ConfigLoader(config_path=config_file)
        loader2 = ConfigLoader(config_path=config_file)

        # Assert
        assert loader1 is not loader2
        assert loader1.get("xp.base_journal_xp") == loader2.get("xp.base_journal_xp")

    def test_multiple_get_calls_do_not_reload_within_interval(self, tmp_path: Path) -> None:
        """Multiple get() calls should not reload within interval."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("xp:\n  base_journal_xp: 100")

        loader = ConfigLoader(config_path=config_file)
        original_mtime = loader._last_modified

        config_file.write_text("xp:\n  base_journal_xp: 200")

        loader._last_check = time.time()

        assert loader.get("xp.base_journal_xp") == 100
        assert loader._last_modified == original_mtime
