"""Production-ready services around the unchanged Observe-Policy-Act-Verify loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from terminal_agent.config import Settings
from terminal_agent.observability.audit import AuditLogger
from terminal_agent.observability.metrics import RuntimeMetrics
from terminal_agent.orchestration.circuit import DomainCircuitBreaker
from terminal_agent.orchestration.dead_letter import DeadLetterQueue
from terminal_agent.orchestration.quota import QuotaGovernor
from terminal_agent.policy.rules import GovernanceRules


def rules_from_settings(settings: Settings) -> GovernanceRules:
    raw = (settings.high_risk_capabilities or "").strip()
    high_risk = frozenset(part.strip() for part in raw.split(",") if part.strip())
    start = settings.work_hours_start
    end = settings.work_hours_end
    return GovernanceRules(
        execution_environment=(settings.execution_environment or "sim").lower(),
        deny_writes=bool(settings.deny_writes),
        high_risk_capabilities=high_risk,
        work_hours_start=start if start is not None and start >= 0 else None,
        work_hours_end=end if end is not None and end >= 0 else None,
    )


@dataclass
class PlatformServices:
    quota: QuotaGovernor
    circuit: DomainCircuitBreaker
    dead_letters: DeadLetterQueue
    metrics: RuntimeMetrics
    audit: AuditLogger
    rules: GovernanceRules

    def reset_eval_isolation(self) -> None:
        """Eval cases inject faults; do not leak circuit state across seeds."""
        self.circuit.reset()

    def snapshot(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics.snapshot(),
            "circuit": self.circuit.snapshot(),
            "execution_environment": self.rules.execution_environment,
            "deny_writes": self.rules.deny_writes,
        }

    @classmethod
    def from_settings(cls, settings: Settings) -> PlatformServices:
        settings.ensure_dirs()
        return cls(
            quota=QuotaGovernor(settings.max_concurrent_runs, settings.max_runs_per_minute),
            circuit=DomainCircuitBreaker(settings.circuit_breaker_failures),
            dead_letters=DeadLetterQueue(),
            metrics=RuntimeMetrics(),
            audit=AuditLogger(settings.audit_log_dir),
            rules=rules_from_settings(settings),
        )


def sanitize_tenant_id(value: str | None, default: str = "local") -> str:
    raw = (value or default or "local").strip() or "local"
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)[:64]
    return cleaned or "local"
