"""Additional branch tests for src.ai.runtime_config."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.ai.runtime_config as runtime_config


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    runtime_config._load_ai_config.cache_clear()
    yield
    runtime_config._load_ai_config.cache_clear()


def test_int_or_default_and_float_or_default_error_paths() -> None:
    assert runtime_config._int_or_default("bad", 17) == 17
    assert runtime_config._float_or_default("bad", 2.5) == 2.5


def test_load_ai_config_handles_yaml_import_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "dev.yaml"
    cfg.write_text("ai: {ollama: {model: llama3.2:latest}}", encoding="utf-8")
    monkeypatch.setenv("CONFIG_PATH", str(cfg))

    real_import = __import__

    def _import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _import)
    assert runtime_config._load_ai_config() == {}
