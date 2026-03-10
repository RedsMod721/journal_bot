"""Runtime configuration helpers for src/ai clients."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "dev.yaml"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@lru_cache(maxsize=1)
def _load_ai_config() -> dict[str, Any]:
    config_path = Path(os.getenv("CONFIG_PATH", str(_DEFAULT_CONFIG)))
    if not config_path.exists():
        return {}

    try:
        import yaml  # type: ignore[import-untyped]
    except Exception:
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except Exception:
        return {}

    if not isinstance(payload, dict):
        return {}

    ai_cfg = _as_dict(payload.get("ai"))
    return {
        "ollama": _as_dict(ai_cfg.get("ollama")),
        "qdrant": _as_dict(ai_cfg.get("qdrant")),
    }


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def get_ollama_defaults() -> tuple[str, str, float]:
    cfg = _as_dict(_load_ai_config().get("ollama"))
    base_url = str(
        os.getenv("OLLAMA_BASE_URL") or cfg.get("base_url") or "http://localhost:11434"
    )
    model = str(os.getenv("OLLAMA_MODEL") or cfg.get("model") or "llama3.2:3b")
    timeout = _float_or_default(
        os.getenv("OLLAMA_TIMEOUT") or cfg.get("timeout") or 30.0,
        30.0,
    )
    return base_url, model, timeout


def get_qdrant_defaults() -> dict[str, Any]:
    cfg = _as_dict(_load_ai_config().get("qdrant"))

    host = str(os.getenv("QDRANT_HOST") or cfg.get("host") or "localhost")
    port = _int_or_default(os.getenv("QDRANT_PORT") or cfg.get("port") or 6333, 6333)
    collection = str(
        os.getenv("QDRANT_COLLECTION") or cfg.get("collection") or "rag_documents"
    )
    vector_size = _int_or_default(
        os.getenv("QDRANT_VECTOR_SIZE") or cfg.get("vector_size") or 768,
        768,
    )
    mode = str(os.getenv("QDRANT_MODE") or cfg.get("mode") or "remote").lower()

    raw_local_path = os.getenv("QDRANT_LOCAL_PATH") or cfg.get(
        "local_path", "data/qdrant_local"
    )
    local_path = Path(str(raw_local_path))
    if not local_path.is_absolute():
        local_path = (_REPO_ROOT / local_path).resolve()

    return {
        "host": host,
        "port": port,
        "collection": collection,
        "vector_size": vector_size,
        "mode": mode,
        "local_path": str(local_path),
    }
