# backend/app/utils/cache.py

from __future__ import annotations

import time
from typing import Any


class TTLCache:
    """In-memory key-value cache with per-entry TTL. Not thread-safe (single process)."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        # WHY tuple value: (payload, expires_at) lets us check expiry without a
        # separate dict, keeping the data structure flat and O(1) per operation.
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (value, time.monotonic() + self._ttl)

    def clear(self) -> None:
        self._store.clear()
