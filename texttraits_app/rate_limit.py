from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowRateLimiter:
    def __init__(self, window_seconds: int = 60, max_keys: int = 10000) -> None:
        self.window_seconds = max(1, int(window_seconds))
        self.max_keys = max(100, int(max_keys))
        self._buckets: dict[str, deque[float]] = {}
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()
        self._last_cleanup = 0.0

    def allow(self, key: str, limit: int, now: float | None = None) -> tuple[bool, int]:
        current = time.monotonic() if now is None else float(now)
        safe_limit = max(1, int(limit))
        with self._lock:
            if current - self._last_cleanup >= self.window_seconds:
                self._cleanup(current)
            if key not in self._buckets and len(self._buckets) >= self.max_keys:
                oldest = min(self._last_seen, key=self._last_seen.get)
                self._buckets.pop(oldest, None)
                self._last_seen.pop(oldest, None)
            bucket = self._buckets.setdefault(key, deque())
            cutoff = current - self.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            self._last_seen[key] = current
            if len(bucket) >= safe_limit:
                retry_after = max(1, int(self.window_seconds - (current - bucket[0])))
                return False, retry_after
            bucket.append(current)
            return True, 0

    def _cleanup(self, current: float) -> None:
        cutoff = current - self.window_seconds
        stale = [key for key, seen_at in self._last_seen.items() if seen_at <= cutoff]
        for key in stale:
            self._buckets.pop(key, None)
            self._last_seen.pop(key, None)
        self._last_cleanup = current

    @property
    def key_count(self) -> int:
        with self._lock:
            return len(self._buckets)
