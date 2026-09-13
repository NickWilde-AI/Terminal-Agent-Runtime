"""Capability-domain circuit breaker. Writes are never auto-retried."""

from __future__ import annotations

from threading import Lock


def _domain(capability_id: str) -> str:
    return capability_id.split(".", 1)[0] if capability_id else "unknown"


class DomainCircuitBreaker:
    def __init__(self, failure_threshold: int = 0) -> None:
        self.failure_threshold = failure_threshold
        self._failures: dict[str, int] = {}
        self._open: set[str] = set()
        self._lock = Lock()

    def enabled(self) -> bool:
        return self.failure_threshold > 0

    def allow(self, capability_id: str) -> bool:
        if not self.enabled():
            return True
        with self._lock:
            return _domain(capability_id) not in self._open

    def record_success(self, capability_id: str) -> None:
        if not self.enabled():
            return
        domain = _domain(capability_id)
        with self._lock:
            self._failures[domain] = 0
            self._open.discard(domain)

    def record_failure(self, capability_id: str) -> bool:
        """Return True if this failure opened the circuit."""
        if not self.enabled():
            return False
        domain = _domain(capability_id)
        with self._lock:
            count = self._failures.get(domain, 0) + 1
            self._failures[domain] = count
            if count >= self.failure_threshold:
                self._open.add(domain)
                return True
            return False

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
            self._open.clear()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {"open_domains": sorted(self._open), "failures": dict(self._failures)}
