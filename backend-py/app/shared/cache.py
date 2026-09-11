"""Tiny in-memory TTL cache for single-process caching, equivalent to the
ad hoc `Map`-based caches in company.service.ts (5 min) and report.service.ts
(60s). Not shared across processes - matches the TS behavior, which was
also per-process, in-memory only.
"""

from __future__ import annotations

import time
from typing import Any


class TtlCache:
    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()
