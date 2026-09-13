"""Append-only JSONL audit trail. Never persist secrets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from terminal_agent.contracts import now

_SECRET_KEYS = {"api_key", "apikey", "authorization", "password", "secret", "token", "credential"}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in _SECRET_KEYS or "api_key" in str(key).lower():
                out[key] = "***"
            else:
                out[key] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class AuditLogger:
    def __init__(self, directory: str = "./data/audit") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "audit.jsonl"

    def emit(
        self,
        action: str,
        *,
        tenant_id: str = "local",
        actor: str = "anonymous",
        run_id: str | None = None,
        result: str = "ok",
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = {
            "at": now().isoformat(),
            "action": action,
            "tenant_id": tenant_id,
            "actor": actor,
            "run_id": run_id,
            "result": result,
            "detail": _redact(detail or {}),
        }
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
        return record

    def tail(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in lines[-max(1, limit) :]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
