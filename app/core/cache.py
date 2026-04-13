from __future__ import annotations

import time
from threading import RLock


class TTLCache:
    def __init__(self):
        self._data = {}
        self._lock = RLock()

    def get(self, key, default=None):
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if not item:
                return default
            expires_at, value = item
            if expires_at < now:
                self._data.pop(key, None)
                return default
            return value

    def set(self, key, value, timeout=300):
        with self._lock:
            self._data[key] = (time.time() + max(1, int(timeout)), value)
        return value

    def delete(self, key):
        with self._lock:
            self._data.pop(key, None)

    def clear(self):
        with self._lock:
            self._data.clear()


def make_key(*parts):
    return '|'.join(str(x) for x in parts)


cache = TTLCache()
