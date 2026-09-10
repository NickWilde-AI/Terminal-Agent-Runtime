"""SQLite run/device snapshots and read-only restart recovery."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from terminal_agent.contracts import Attribution, ExecutionStatus, RunLifecycle, RunPhase, RunRecord
from terminal_agent.device.simulator import DeviceSimulator
from terminal_agent.persistence.store import InMemoryRunStore


class SqlitePersistence:
    def __init__(
        self,
        store: InMemoryRunStore,
        simulator: DeviceSimulator,
        path: str = "./data/device-agent.db",
        enabled: bool = False,
    ) -> None:
        self.store, self.simulator, self.path, self.enabled = store, simulator, Path(path), enabled
        self._lock = asyncio.Lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    async def init(self) -> None:
        if not self.enabled:
            return
        self.path.absolute().parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._create_tables)
        device_payload, run_payloads = await asyncio.to_thread(self._load)
        if device_payload:
            await self.simulator.restore(json.loads(device_payload))
        await self.simulator.terminate_queued_actions()
        recovered = [RunRecord.model_validate_json(payload) for payload in run_payloads]
        self.store.on_persist(self.persist_run)
        self.simulator.on_persist(self.persist_device)
        await self.persist_device(self.simulator.export_state())
        for run in recovered:
            self.store.save(run)
            interrupted = not run.is_terminal()
            if interrupted:
                run.lifecycle, run.phase, run.pending = RunLifecycle.INTERRUPTED, RunPhase.FINISH, None
                run.stop_reason = "PROCESS_RESTART"
                run.result_summary = "进程重启中断；旧确认失效，仅只读对账，不自动续跑"
            if interrupted or run.unresolved_unknown:
                reads, unknown = 0, False
                for action in run.actions:
                    if action.execution_status in (ExecutionStatus.PROPOSED, ExecutionStatus.AUTHORIZED):
                        action.execution_status = ExecutionStatus.CANCELLED_BEFORE_DISPATCH
                        continue
                    if action.execution_status not in (
                        ExecutionStatus.DISPATCHED,
                        ExecutionStatus.UNKNOWN,
                        ExecutionStatus.ACKNOWLEDGED,
                    ):
                        continue
                    record = await self.simulator.query_action(action.action_id) if reads < 4 else None
                    reads += 1
                    if record is None:
                        action.execution_status, unknown = ExecutionStatus.UNKNOWN, True
                    else:
                        action.execution_status = (
                            ExecutionStatus.APPLIED if record.status == "APPLIED" else ExecutionStatus.NOT_APPLIED
                        )
                        action.attribution = (
                            Attribution.THIS_ACTION if record.status == "APPLIED" else Attribution.UNKNOWN
                        )
                        action.evidence["recovery_device_record"] = record.model_dump(mode="json")
                    await self.store.append_event(
                        run,
                        "RECOVERY_READ",
                        {"action_id": action.action_id, "status": action.execution_status.value, "origin": "RECOVERY"},
                    )
                run.unresolved_unknown = unknown
                if not unknown:
                    run.in_flight_action_id = None
                await self.store.append_event(
                    run,
                    "RECOVERED_READ_ONLY",
                    {"interrupted": interrupted, "unresolved": unknown, "reads": min(reads, 4)},
                )
            await self.persist_run(run)

    def _create_tables(self) -> None:
        with self._connect() as connection:
            connection.execute("create table if not exists v2_runs(id text primary key,payload text not null)")
            connection.execute("create table if not exists v2_device(id integer primary key,payload text not null)")

    def _load(self) -> tuple[str | None, list[str]]:
        with self._connect() as connection:
            device = connection.execute("select payload from v2_device where id=1").fetchone()
            runs = connection.execute("select payload from v2_runs").fetchall()
        return (device[0] if device else None, [row[0] for row in runs])

    async def _save(self, table: str, id_: str | int, payload: str) -> None:
        if not self.enabled:
            return
        async with self._lock:
            try:
                await asyncio.to_thread(self._save_sync, table, id_, payload)
            except (OSError, sqlite3.Error) as exc:
                raise RuntimeError("SQLITE_STORAGE_UNAVAILABLE") from exc

    def _save_sync(self, table: str, id_: str | int, payload: str) -> None:
        with self._connect() as connection:
            connection.execute(
                f"insert into {table}(id,payload) values(?,?) on conflict(id) do update set payload=excluded.payload",
                (id_, payload),
            )

    async def persist_run(self, run: RunRecord) -> None:
        await self._save("v2_runs", run.run_id, run.model_dump_json())

    async def persist_device(self, data: dict[str, Any]) -> None:
        await self._save("v2_device", 1, json.dumps(data, ensure_ascii=False, default=str))

    def list_interrupted_snapshots(self) -> list[dict[str, str]]:
        return [
            {"run_id": run.run_id, "lifecycle": "INTERRUPTED"}
            for run in self.store.list()
            if run.lifecycle == RunLifecycle.INTERRUPTED
        ]
