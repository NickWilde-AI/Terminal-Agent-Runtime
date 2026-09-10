"""Capability schema, constraint and confirmation policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from terminal_agent.capability.core import CapabilityRegistry
from terminal_agent.contracts import PolicyDecision, RunRecord


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    code: str | None = None
    message: str | None = None


class PolicyEngine:
    def __init__(self, registry: CapabilityRegistry, require_confirmation: bool = False) -> None:
        self.registry, self.require_confirmation = registry, require_confirmation

    def decide(self, run: RunRecord, capability_id: str, params: dict[str, Any]) -> PolicyResult:
        validation = self.registry.validate(capability_id, params)
        if not validation.ok:
            return PolicyResult(PolicyDecision.DENY, validation.code, validation.message)
        for constraint in run.task.constraints:
            type_ = str(constraint.get("type", ""))
            if type_ == "forbid_action" and capability_id == str(constraint.get("capability_id")):
                return PolicyResult(PolicyDecision.DENY, "FORBIDDEN", f"约束禁止分发: {capability_id}")
            if type_ == "no_cabin_write" and capability_id.startswith(("cabin.", "climate.")):
                return PolicyResult(PolicyDecision.DENY, "FORBIDDEN", "约束：不调空调")
            if type_ == "no_media_write" and capability_id.startswith("media."):
                return PolicyResult(PolicyDecision.DENY, "FORBIDDEN", "约束：不改媒体")
            if type_ == "no_window" and "window" in capability_id:
                return PolicyResult(PolicyDecision.DENY, "FORBIDDEN", "约束：不要开窗")
            if type_ == "no_reboot" and "reboot" in capability_id:
                return PolicyResult(PolicyDecision.DENY, "FORBIDDEN", "约束：不要重启")
        candidate_device = params.get("device_id")
        if candidate_device is not None and run.device_id != str(candidate_device):
            return PolicyResult(PolicyDecision.DENY, "DEVICE_MISMATCH", "候选设备不属于当前会话授权设备")
        authorized = run.task.binding_context.get("authorized_device_id")
        if authorized is not None and run.device_id != str(authorized):
            return PolicyResult(PolicyDecision.DENY, "DEVICE_MISMATCH", "会话未授权该设备")
        definition = self.registry.get(capability_id)
        if (
            self.require_confirmation
            and definition
            and definition.write
            and not run.task.binding_context.get("force_allow_write")
        ):
            approved = run.task.binding_context.get("approved_action")
            if isinstance(approved, dict) and approved == {
                "capability_id": capability_id,
                "params": params,
                "goal_version": run.task.goal_version,
            }:
                del run.task.binding_context["approved_action"]
                return PolicyResult(PolicyDecision.ALLOW)
            return PolicyResult(PolicyDecision.REQUIRE_CONFIRMATION, "REQUIRE_CONFIRMATION", "演示策略：写操作需确认")
        return PolicyResult(PolicyDecision.ALLOW)
