from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    """Simple threadsafe TTL+LRU cache for service-layer computed summaries."""

    def __init__(self, max_entries: int = 128, ttl_seconds: int = 120) -> None:
        self.max_entries = max(8, int(max_entries))
        self.ttl_seconds = max(5, int(ttl_seconds))
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at < now:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.time() + self.ttl_seconds, value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            keys = [k for k in self._data.keys() if k.startswith(prefix)]
            for k in keys:
                self._data.pop(k, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
