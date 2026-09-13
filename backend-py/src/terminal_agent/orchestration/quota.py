"""Per-tenant admission control. Rate limit 0 disables the window check."""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic


class QuotaGovernor:
    def __init__(self, max_concurrent_runs: int = 8, max_runs_per_minute: int = 0) -> None:
        self.max_concurrent_runs = max_concurrent_runs
        self.max_runs_per_minute = max_runs_per_minute
        self._created: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, tenant_id: str, active_runs: int) -> str | None:
        if self.max_concurrent_runs > 0 and active_runs >= self.max_concurrent_runs:
            return "TENANT_QUOTA_CONCURRENT"
        if self.max_runs_per_minute <= 0:
            return None
        now = monotonic()
        with self._lock:
            window = self._created[tenant_id]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self.max_runs_per_minute:
                return "TENANT_QUOTA_RATE"
        return None

    def note_created(self, tenant_id: str) -> None:
        with self._lock:
            self._created[tenant_id].append(monotonic())
