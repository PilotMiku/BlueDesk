"""Bounds and rate limits applied before untrusted Bluetooth data reaches Qt."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict

MAX_DEVICES = 512
NEARBY_TTL = 120
MAX_NAME_CHARS = 256
MAX_GATT_BYTES = 512
MAX_SERVICES = 64
MAX_CHARACTERISTICS = 512
MAX_OUTPUT_BLOCKS = 500


class RateLimiter:
    """Bounded per-key fixed windows, with a global caller-supplied key option."""

    def __init__(self, limit: int, interval: float = 1.0, max_keys: int = MAX_DEVICES):
        self.limit = limit
        self.interval = interval
        self.max_keys = max_keys
        self._windows: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            start, count = self._windows.get(key, (now, 0))
            if now - start >= self.interval:
                start, count = now, 0
            if count >= self.limit:
                return False
            if key not in self._windows and len(self._windows) >= self.max_keys:
                self._windows.popitem(last=False)
            self._windows[key] = (start, count + 1)
            self._windows.move_to_end(key)
            return True
