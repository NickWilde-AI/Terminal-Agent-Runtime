"""Domain model facade — re-export the single source in terminal_agent.contracts."""

from __future__ import annotations

from terminal_agent.contracts import (
    AgentRole,
    ChangeSource,
    Criterion,
    DeviceDomain,
    DeviceTask,
    ReviewDecision,
    RouteType,
    StateSnapshot,
)

__all__ = [
    "AgentRole",
    "ChangeSource",
    "Criterion",
    "DeviceDomain",
    "DeviceTask",
    "ReviewDecision",
    "RouteType",
    "StateSnapshot",
]
