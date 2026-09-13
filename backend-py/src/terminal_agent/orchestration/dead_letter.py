"""Failed / interrupted runs for human resume. Never auto-replays writes."""

from __future__ import annotations

from threading import Lock
from typing import Any

from terminal_agent.contracts import RunRecord, now


class DeadLetterQueue:
    def __init__(self, limit: int = 200) -> None:
        self.limit = limit
        self._items: list[dict[str, Any]] = []
        self._lock = Lock()

    def add(self, run: RunRecord, reason: str) -> None:
        item = {
            "at": now().isoformat(),
            "run_id": run.run_id,
            "tenant_id": run.tenant_id,
            "lifecycle": run.lifecycle.value,
            "stop_reason": run.stop_reason,
            "reason": reason,
            "unresolved_unknown": run.unresolved_unknown,
            "note": "只读入队，禁止自动重放写动作",
        }
        with self._lock:
            self._items.append(item)
            if len(self._items) > self.limit:
                self._items = self._items[-self.limit :]

    def list(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._items)
        if tenant_id:
            items = [item for item in items if item.get("tenant_id") == tenant_id]
        return list(reversed(items))
