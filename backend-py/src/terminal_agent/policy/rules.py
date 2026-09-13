"""Deterministic governance rules. Defaults keep Fake eval behavior unchanged."""

from __future__ import annotations

from dataclasses import dataclass, field

from terminal_agent.contracts import now


@dataclass(frozen=True)
class GovernanceRules:
    execution_environment: str = "sim"
    deny_writes: bool = False
    prod_forbidden_prefixes: tuple[str, ...] = ("system.", "debug.", "experiment.")
    high_risk_capabilities: frozenset[str] = field(default_factory=frozenset)
    work_hours_start: int | None = None
    work_hours_end: int | None = None

    def writes_paused(self) -> bool:
        return self.deny_writes

    def forbidden_in_environment(self, capability_id: str) -> bool:
        if self.execution_environment not in {"prod", "production"}:
            return False
        return any(capability_id.startswith(prefix) for prefix in self.prod_forbidden_prefixes)

    def outside_work_hours(self) -> bool:
        if self.work_hours_start is None or self.work_hours_end is None:
            return False
        hour = now().hour
        start, end = self.work_hours_start, self.work_hours_end
        if start == end:
            return True
        if start < end:
            return not (start <= hour < end)
        return not (hour >= start or hour < end)

    def requires_confirmation(self, capability_id: str) -> bool:
        return capability_id in self.high_risk_capabilities
