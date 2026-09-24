import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CacheEntry:
    value: Any
    stored_at: float
    ttl: float

    @property
    def expired(self) -> bool:
        return (time.time() - self.stored_at) > self.ttl

    @property
    def retrieved_at_iso(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(self.stored_at))


class TTLCache:
    """A tiny in-memory TTL cache. Good enough for a single-process MVP.

    Swap this out for Redis if the app scales past one worker process, since
    an in-memory cache is per-process and won't be shared across workers.
    """

    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[CacheEntry]:
        entry = self._store.get(key)
        if entry is None or entry.expired:
            return None
        return entry

    def set(self, key: str, value: Any, ttl: float) -> CacheEntry:
        entry = CacheEntry(value=value, stored_at=time.time(), ttl=ttl)
        self._store[key] = entry
        return entry

    def stats(self) -> dict:
        return {
            "keys_cached": len(self._store),
            "keys": list(self._store.keys()),
        }


cache = TTLCache()
