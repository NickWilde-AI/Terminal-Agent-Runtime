"""Device adapter boundary and adapter-neutral errors."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from terminal_agent.contracts import ActionRecord, DeviceDomain, StateSnapshot


class FaultType(StrEnum):
    NONE = "NONE"
    REJECT = "REJECT"
    ACK_NOT_APPLIED = "ACK_NOT_APPLIED"
    APPLIED_RESPONSE_LOST = "APPLIED_RESPONSE_LOST"
    DELAY_APPLY = "DELAY_APPLY"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    READ_FAIL = "READ_FAIL"
    STALE_STATE = "STALE_STATE"


class DeviceException(RuntimeError):
    def __init__(self, code: str, message: str, action_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.action_id = action_id


class DevicePort(Protocol):
    @property
    def device_id(self) -> str: ...
    @property
    def environment_id(self) -> str: ...
    async def read_state(self, domains: set[DeviceDomain] | None = None) -> StateSnapshot: ...
    async def snapshot(self) -> StateSnapshot: ...
    async def view(self) -> dict[str, Any]: ...
    async def apply_write(
        self,
        action_id: str,
        idempotency_key: str,
        capability_id: str,
        params: dict[str, Any],
        environment_id: str,
        deadline: datetime | None,
        expected_revisions: dict[str, int],
        run_id: str | None,
        goal_version: int,
    ) -> ActionRecord: ...
    async def query_action(self, action_id: str) -> ActionRecord | None: ...
    async def reset_to_defaults(self) -> None: ...
    async def force_new_environment(self) -> None: ...
    async def inject_fault(self, type_: FaultType, capability_id: str | None, times: int) -> None: ...
    async def clear_fault(self) -> None: ...
    async def apply_initial_state(self, fields: dict[str, Any]) -> None: ...
    async def external_change(self, field: str, value: Any) -> None: ...
    def add_change_listener(self, listener: Callable[[dict[str, Any]], Any]) -> None: ...
    def on_persist(self, sink: Callable[[dict[str, Any]], Any]) -> None: ...
