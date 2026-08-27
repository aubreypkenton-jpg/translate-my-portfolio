"""
Tiny in-memory TTL cache for fetched price data.

This is a personal-scale app running as a single process, so a plain dict
with timestamps is sufficient -- no Redis needed. If this ever runs behind
multiple worker processes, this cache stops being shared across them and
should be swapped for something external. Documented in DECISIONS.md.
"""
import time


class TTLCache:
    def __init__(self, ttl_seconds):
        self.ttl = ttl_seconds
        self._store = {}

    def get(self, key):
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key, value):
        self._store[key] = (value, time.time() + self.ttl)

    def clear(self):
        self._store.clear()
