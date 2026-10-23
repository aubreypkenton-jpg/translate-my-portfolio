"""
Tiny in-memory TTL (time-to-live) cache for fetched market data.

This app runs as a single small process, so a dict with expiry timestamps is
enough: no Redis needed. A lock makes it safe for the thread pool in
data_fetch.py, and ``max_entries`` stops it growing without limit if many
different tickers are requested. If this ever runs as several processes the
cache stops being shared between them (see DECISIONS.md).
"""
from __future__ import annotations

import threading
import time
from typing import Any


class TTLCache:
    """A thread-safe dict whose entries expire after ``ttl_seconds``."""

    def __init__(self, ttl_seconds: float, max_entries: int = 1000) -> None:
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """Return the cached value, or None if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.time() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        """Store ``value``; evicts the soonest-to-expire entry if full."""
        with self._lock:
            if key not in self._store and len(self._store) >= self.max_entries:
                oldest = min(self._store, key=lambda k: self._store[k][1])
                del self._store[oldest]
            self._store[key] = (value, time.time() + self.ttl)

    def delete(self, key: str) -> None:
        """Remove one entry if present."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
