import time
from threading import RLock
from typing import Any


class ProviderCache:
    """Small thread-safe TTL cache with provider-specific namespaces."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[tuple[str, str], tuple[float, Any]] = {}
        self._lock = RLock()

    def get(self, provider: str, key: str) -> Any | None:
        cache_key = (provider, key)
        with self._lock:
            item = self._items.get(cache_key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= time.monotonic():
                self._items.pop(cache_key, None)
                return None
            return value

    def set(self, provider: str, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        with self._lock:
            self._items[(provider, key)] = (time.monotonic() + ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()