from __future__ import annotations

import time
from threading import RLock


class TTLCache:
    def __init__(self, max_entries: int | None = None):
        self._data = {}
        self._lock = RLock()
        self._max_entries = max_entries

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
            if self._max_entries is not None and len(self._data) > self._max_entries:
                # Отбрасываем просроченные и самые старые по expires_at
                now = time.time()
                # 1) выбрасываем все истёкшие
                for k, (exp, _) in list(self._data.items()):
                    if exp < now:
                        self._data.pop(k, None)
                # 2) если всё ещё превышен лимит — режем самые старые (min expires_at)
                while len(self._data) > self._max_entries:
                    oldest_key = min(self._data.items(), key=lambda kv: kv[1][0])[0]
                    self._data.pop(oldest_key, None)
        return value

    def delete(self, key):
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix: str):
        with self._lock:
            for k in list(self._data.keys()):
                if isinstance(k, str) and k.startswith(prefix):
                    self._data.pop(k, None)

    def clear(self):
        with self._lock:
            self._data.clear()


def make_key(*parts):
    return '|'.join(str(x) for x in parts)


cache = TTLCache()

# Отдельный кеш готовых HTML-ответов для тяжёлых реестров (/social-passport, /classes).
# max_entries=16 гарантирует, что при ~8 МБ на запись потребление < 150 МБ.
view_response_cache = TTLCache(max_entries=16)
