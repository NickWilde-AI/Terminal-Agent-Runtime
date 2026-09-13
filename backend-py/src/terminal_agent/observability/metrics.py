"""In-process runtime counters. Prometheus scrape can wrap snapshot() later."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class RuntimeMetrics:
    runs_created: int = 0
    runs_completed: int = 0
    runs_cancelled: int = 0
    runs_failed: int = 0
    runs_interrupted: int = 0
    writes_denied: int = 0
    quota_rejected: int = 0
    circuit_open: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def inc(self, name: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + amount)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "runs_created": self.runs_created,
                "runs_completed": self.runs_completed,
                "runs_cancelled": self.runs_cancelled,
                "runs_failed": self.runs_failed,
                "runs_interrupted": self.runs_interrupted,
                "writes_denied": self.writes_denied,
                "quota_rejected": self.quota_rejected,
                "circuit_open": self.circuit_open,
            }
