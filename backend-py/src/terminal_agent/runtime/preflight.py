"""Zero-LLM Plan / Action Preflight. Not an Agent."""

from __future__ import annotations

from typing import Any

from terminal_agent.capability.core import CapabilityRegistry, effects_match
from terminal_agent.contracts import (
    ExecutionStatus,
    PlanDraft,
    PreflightDecision,
    PreflightResult,
    ReviewDecision,
    RunRecord,
    StateSnapshot,
    TaskSpec,
)
from terminal_agent.policy.engine import PolicyEngine, PolicyResult
from terminal_agent.contracts import PolicyDecision


class PreflightGate:
    def __init__(self, registry: CapabilityRegistry, policy: PolicyEngine) -> None:
        self.registry = registry
        self.policy = policy

    def check_plan(self, run: RunRecord, spec: TaskSpec, draft: PlanDraft) -> PreflightResult:
        if run.is_terminal() or run.cancel_accepted or spec.goal_version != run.task.goal_version:
            return PreflightResult(
                decision=PreflightDecision.STALE, code="STALE", message="目标版本或任务已失效", level="PLAN"
            )
        from terminal_agent.agent.multi_agent import review

        inspected = review(spec, draft, spec.model_id)
        if inspected.violated_constraints or inspected.risky_actions:
            return PreflightResult(
                decision=PreflightDecision.DENY,
                code="PLAN_VIOLATION",
                message="计划违反约束或超出允许能力",
                missing_goals=list(inspected.missing_goals),
                violated_constraints=list(inspected.violated_constraints),
                risky_actions=list(inspected.risky_actions),
                level="PLAN",
            )
        if inspected.decision == ReviewDecision.REVISE or inspected.missing_goals:
            return PreflightResult(
                decision=PreflightDecision.DENY,
                code="PLAN_COVERAGE",
                message="计划未覆盖结构化目标",
                missing_goals=list(inspected.missing_goals),
                level="PLAN",
            )
        for action in draft.actions:
            cap = str(action.get("capability_id") or "")
            params = dict(action.get("params") or {})
            peeked = self.policy.decide(run, cap, params, consume_approval=False)
            if peeked.decision == PolicyDecision.REQUIRE_CONFIRMATION:
                return PreflightResult(
                    decision=PreflightDecision.WAIT_CONFIRMATION,
                    code="WAIT_CONFIRMATION",
                    message=peeked.message or "计划含需确认的写操作",
                    level="PLAN",
                )
            if peeked.decision == PolicyDecision.DENY:
                return PreflightResult(
                    decision=PreflightDecision.DENY,
                    code=peeked.code or "POLICY_DENIED",
                    message=peeked.message or "计划动作被策略拒绝",
                    violated_constraints=[peeked.message or peeked.code or cap],
                    level="PLAN",
                )
        return PreflightResult(decision=PreflightDecision.ALLOW, level="PLAN")

    def check_action(
        self,
        run: RunRecord,
        capability_id: str,
        params: dict[str, Any],
        snapshot: StateSnapshot,
        version: int,
    ) -> PreflightResult:
        if run.is_terminal() or run.cancel_accepted or version != run.task.goal_version:
            return PreflightResult(
                decision=PreflightDecision.STALE, code="STALE", message="目标版本或任务已失效", level="ACTION"
            )
        if run.budget.expired():
            return PreflightResult(
                decision=PreflightDecision.DENY, code="BUDGET_EXPIRED", message="任务已到期", level="ACTION"
            )
        if run.budget.write_actions >= run.budget.max_write_actions:
            return PreflightResult(
                decision=PreflightDecision.DENY, code="BUDGET_EXHAUSTED_WRITE", message="写操作预算已用尽", level="ACTION"
            )
        if capability_id in ("device.get_state", "device.read_state"):
            return PreflightResult(decision=PreflightDecision.ALLOW, skip_write=True, level="ACTION")
        if any(
            a.capability_id == capability_id
            and a.params == params
            and a.execution_status == ExecutionStatus.APPLIED
            and a.goal_version == version
            for a in run.actions
        ):
            return PreflightResult(
                decision=PreflightDecision.ALLOW,
                skip_write=True,
                code="IDEMPOTENT",
                message="相同写操作已应用",
                level="ACTION",
            )
        if effects_match(capability_id, params, snapshot.state):
            return PreflightResult(
                decision=PreflightDecision.ALLOW,
                skip_write=True,
                code="ALREADY_SATISFIED",
                message="当前状态已满足预期效果",
                level="ACTION",
            )
        peeked: PolicyResult = self.policy.decide(run, capability_id, params, consume_approval=False)
        if peeked.decision == PolicyDecision.DENY:
            return PreflightResult(
                decision=PreflightDecision.DENY,
                code=peeked.code or "POLICY_DENIED",
                message=peeked.message,
                level="ACTION",
            )
        if peeked.decision == PolicyDecision.REQUIRE_CONFIRMATION:
            return PreflightResult(
                decision=PreflightDecision.WAIT_CONFIRMATION,
                code="WAIT_CONFIRMATION",
                message=peeked.message,
                level="ACTION",
            )
        return PreflightResult(decision=PreflightDecision.ALLOW, level="ACTION")
