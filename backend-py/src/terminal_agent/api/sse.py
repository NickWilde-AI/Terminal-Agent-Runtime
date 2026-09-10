"""SSE fan-out for run events and device state."""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from sse_starlette.sse import EventSourceResponse

from terminal_agent.contracts import RunLifecycle, RuntimeEvent
from terminal_agent.device.simulator import DeviceSimulator
from terminal_agent.persistence.store import InMemoryRunStore
from terminal_agent.runtime.harness import HarnessService

_TERMINAL = {
    RunLifecycle.COMPLETED,
    RunLifecycle.FAILED,
    RunLifecycle.STOPPED,
    RunLifecycle.CANCELLED,
    RunLifecycle.TIMED_OUT,
    RunLifecycle.INTERRUPTED,
    RunLifecycle.PARTIAL,
}


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


class SseHub:
    def __init__(
        self, store: InMemoryRunStore, simulator: DeviceSimulator, harness: HarnessService
    ) -> None:
        self.store = store
        self.simulator = simulator
        self.harness = harness
        self._run_queues: dict[str, list[asyncio.Queue[dict[str, Any] | None]]] = defaultdict(list)
        self._device_queues: list[asyncio.Queue[dict[str, Any] | None]] = []
        self._heartbeat: asyncio.Task[None] | None = None
        self._wired = False

    def wire(self) -> None:
        if self._wired:
            return
        self.store.add_event_listener(self._on_runtime_event)
        self.simulator.add_change_listener(self._on_device_change)
        self._heartbeat = asyncio.create_task(self._ping_loop(), name="sse-heartbeat")
        self._wired = True

    async def shutdown(self) -> None:
        if self._heartbeat and not self._heartbeat.done():
            self._heartbeat.cancel()
        for queues in self._run_queues.values():
            for q in list(queues):
                await q.put(None)
        for q in list(self._device_queues):
            await q.put(None)
        self._run_queues.clear()
        self._device_queues.clear()

    def subscribe_run(self, run_id: str, after_seq: int = 0) -> EventSourceResponse:
        return EventSourceResponse(self._run_stream(run_id, after_seq))

    def subscribe_device(self) -> EventSourceResponse:
        return EventSourceResponse(self._device_stream())

    async def _run_stream(self, run_id: str, after_seq: int) -> AsyncIterator[dict[str, str]]:
        run = self.store.find(run_id)
        if run is None:
            raise ValueError("run not found")
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._run_queues[run_id].append(queue)
        try:
            for event in self.store.events_after(run_id, after_seq):
                yield {"event": "event", "data": _json(self._event_payload(event))}
            yield {"event": "run", "data": _json(self.harness.to_view(run))}
            yield {"event": "device", "data": _json(await self._device_payload())}
            if run.lifecycle in _TERMINAL:
                return
            while True:
                item = await queue.get()
                if item is None:
                    return
                yield item
                if item.get("event") == "run":
                    life = json.loads(item["data"]).get("lifecycle")
                    if self._is_terminal_lifecycle(life):
                        return
        finally:
            queues = self._run_queues.get(run_id, [])
            if queue in queues:
                queues.remove(queue)
            if not queues:
                self._run_queues.pop(run_id, None)

    async def _device_stream(self) -> AsyncIterator[dict[str, str]]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._device_queues.append(queue)
        try:
            yield {"event": "device", "data": _json(await self._device_payload())}
            while True:
                item = await queue.get()
                if item is None:
                    return
                yield item
        finally:
            if queue in self._device_queues:
                self._device_queues.remove(queue)

    def _on_runtime_event(self, event: RuntimeEvent) -> None:
        queues = list(self._run_queues.get(event.run_id or "", []))
        if not queues:
            return
        run = self.store.find(event.run_id or "")
        run_view = self.harness.to_view(run) if run else None
        payload_event = {"event": "event", "data": _json(self._event_payload(event))}
        for q in queues:
            self._put(q, payload_event)
            if run_view is not None:
                self._put(q, {"event": "run", "data": _json(run_view)})
            self._put(q, {"event": "device", "data": _json(self._device_payload_sync())})

    def _on_device_change(self, view: dict[str, Any]) -> None:
        payload = {"event": "device", "data": _json(self._normalize_device(view))}
        for q in list(self._device_queues):
            self._put(q, payload)
        for queues in list(self._run_queues.values()):
            for q in list(queues):
                self._put(q, payload)

    async def _ping_loop(self) -> None:
        while True:
            await asyncio.sleep(15)
            ping = {"event": "ping", "data": _json({"ts": int(time.time() * 1000)})}
            for queues in list(self._run_queues.values()):
                for q in list(queues):
                    self._put(q, ping)
            for q in list(self._device_queues):
                self._put(q, ping)

    def _put(self, queue: asyncio.Queue[dict[str, Any] | None], item: dict[str, Any]) -> None:
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            pass

    def _event_payload(self, event: RuntimeEvent) -> dict[str, Any]:
        return {
            "seq": event.seq,
            "type": event.type,
            "at": event.at,
            "goalVersion": event.goal_version,
            "actionId": event.action_id,
            "payload": event.payload,
            "runId": event.run_id,
        }

    async def _device_payload(self) -> dict[str, Any]:
        return self._normalize_device(await self.simulator.view())

    def _device_payload_sync(self) -> dict[str, Any]:
        return self._normalize_device(self.simulator._view())  # noqa: SLF001 — mirror Java sync path

    def _normalize_device(self, view: dict[str, Any]) -> dict[str, Any]:
        return {
            "device_id": view.get("device_id", self.simulator.device_id),
            "environment_id": view.get("environment_id"),
            "observed_at": view.get("observed_at"),
            "domain_revisions": view.get("domain_revisions"),
            "state": view.get("state"),
            "simulation": True,
            "note": "本地设备模拟器状态（SSE）",
        }

    @staticmethod
    def _is_terminal_lifecycle(life: Any) -> bool:
        try:
            return RunLifecycle(str(life)) in _TERMINAL
        except Exception:
            return False
