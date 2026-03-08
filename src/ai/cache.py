"""Simple in-memory step cache (24h default TTL)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class _CacheItem:
    value: Any
    expires_at: float


class StepCache:
    def __init__(self, ttl_hours: int = 24) -> None:
        self.ttl_seconds = ttl_hours * 3600
        self._store: dict[str, _CacheItem] = {}

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        if item.expires_at <= time.time():
            self._store.pop(key, None)
            return None
        return item.value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = _CacheItem(
            value=value, expires_at=time.time() + self.ttl_seconds
        )
