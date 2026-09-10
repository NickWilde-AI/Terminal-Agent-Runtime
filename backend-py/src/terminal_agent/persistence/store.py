"""In-memory run index plus durable append-only JSONL event journal."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from terminal_agent.contracts import RunRecord, RuntimeEvent


class InMemoryRunStore:
    def __init__(self, event_log_dir: str = "./data/events") -> None:
        self.runs: dict[str, RunRecord] = {}
        self.requests: dict[str, str] = {}
        self.directory = Path(event_log_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._persistence: Callable[[RunRecord], Any] = lambda _: None
        self._listeners: list[Callable[[RuntimeEvent], Any]] = []
        self._lock = asyncio.Lock()

    def on_persist(self, sink: Callable[[RunRecord], Any]) -> None:
        self._persistence = sink

    def add_event_listener(self, listener: Callable[[RuntimeEvent], Any]) -> None:
        self._listeners.append(listener)

    def remove_event_listener(self, listener: Callable[[RuntimeEvent], Any]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def find_by_request_id(self, id_: str) -> RunRecord | None:
        run_id = self.requests.get(id_)
        return self.runs.get(run_id) if run_id else None

    def find(self, id_: str) -> RunRecord | None:
        return self.runs.get(id_)

    def save(self, run: RunRecord) -> None:
        self.runs[run.run_id] = run
        if run.request_id:
            self.requests[run.request_id] = run.run_id

    def list(self) -> list[RunRecord]:
        return list(self.runs.values())

    def has_active_write_run(self, device_id: str) -> bool:
        return any(
            r.device_id == device_id and (not r.is_terminal() or r.unresolved_unknown) for r in self.runs.values()
        )

    @staticmethod
    async def _invoke(callback: Callable[[Any], Any], value: Any) -> None:
        result = callback(value)
        if inspect.isawaitable(result):
            await result

    async def append_event(self, run: RunRecord, type_: str, payload: dict[str, Any] | None = None) -> RuntimeEvent:
        payload = dict(payload or {})
        async with self._lock:
            event = RuntimeEvent(
                type=type_,
                payload=payload,
                run_id=run.run_id,
                environment_id=run.environment_id,
                goal_version=run.task.goal_version,
                seq=run.events[-1].seq + 1 if run.events else 1,
                action_id=str(payload["action_id"]) if payload.get("action_id") is not None else None,
            )
            run.events.append(event)
            run.touch()
            await self._invoke(self._persistence, run)
            try:
                line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"
                await asyncio.to_thread(_append_text, self.directory / f"{run.run_id}.jsonl", line)
            except OSError as exc:
                raise RuntimeError("EVENT_STORAGE_UNAVAILABLE") from exc
        for listener in list(self._listeners):
            await self._invoke(listener, event)
        return event

    def events_after(self, id_: str, seq: int) -> list[RuntimeEvent]:
        run = self.find(id_)
        return [event for event in run.events if event.seq > seq] if run else []


def _append_text(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(text)
        output.flush()
