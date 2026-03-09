"""Unit tests for src.ai.runtime_config."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

import src.ai.runtime_config as runtime_config


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    runtime_config._load_ai_config.cache_clear()
    yield
    runtime_config._load_ai_config.cache_clear()


def test_load_ai_config_missing_file_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_PATH", "Z:/does/not/exist/dev.yaml")
    assert runtime_config._load_ai_config() == {}


def test_load_ai_config_non_mapping_payload_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "dev.yaml"
    cfg.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    monkeypatch.setenv("CONFIG_PATH", str(cfg))
    assert runtime_config._load_ai_config() == {}


def test_load_ai_config_reads_nested_ai_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "dev.yaml"
    cfg.write_text(
        """
ai:
  ollama:
    base_url: http://x
    model: llama3.2:latest
    timeout: 42
  qdrant:
    host: 127.0.0.1
    port: 6334
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(cfg))

    loaded = runtime_config._load_ai_config()
    assert loaded["ollama"]["model"] == "llama3.2:latest"
    assert loaded["qdrant"]["port"] == 6334


def test_get_ollama_defaults_env_overrides_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "dev.yaml"
    cfg.write_text(
        """
ai:
  ollama:
    base_url: http://config-host:11434
    model: config-model
    timeout: 31
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(cfg))
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://env-host:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "env-model")
    monkeypatch.setenv("OLLAMA_TIMEOUT", "12.5")

    base_url, model, timeout = runtime_config.get_ollama_defaults()
    assert base_url == "http://env-host:11434"
    assert model == "env-model"
    assert timeout == 12.5


def test_get_ollama_defaults_invalid_timeout_uses_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "dev.yaml"
    cfg.write_text("ai: {ollama: {timeout: 33}}", encoding="utf-8")
    monkeypatch.setenv("CONFIG_PATH", str(cfg))
    monkeypatch.setenv("OLLAMA_TIMEOUT", "not-a-float")

    _, _, timeout = runtime_config.get_ollama_defaults()
    assert timeout == 30.0


def test_get_qdrant_defaults_resolves_relative_local_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "dev.yaml"
    cfg.write_text(
        """
ai:
  qdrant:
    host: localhost
    port: 6333
    collection: rag_documents
    vector_size: 384
    mode: local
    local_path: data/qdrant_local
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(cfg))

    out = runtime_config.get_qdrant_defaults()
    assert out["mode"] == "local"
    assert out["local_path"].endswith("data\\qdrant_local") or out["local_path"].endswith(
        "data/qdrant_local"
    )


def test_get_qdrant_defaults_invalid_env_port_uses_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "dev.yaml"
    cfg.write_text("ai: {qdrant: {port: 7000}}", encoding="utf-8")
    monkeypatch.setenv("CONFIG_PATH", str(cfg))
    monkeypatch.setenv("QDRANT_PORT", "bad-port")

    out = runtime_config.get_qdrant_defaults()
    assert out["port"] == 6333
