"""Core domain contracts — Pydantic models mirroring Java runtime semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def dict_of(**kwargs: Any) -> dict[str, Any]:
    """Preserve insertion order; allow None values (unlike some Map.of equivalents)."""
    return dict(kwargs)


class RunLifecycle(StrEnum):
    RECEIVED = "RECEIVED"
    RUNNING = "RUNNING"
    WAITING_CLARIFICATION = "WAITING_CLARIFICATION"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    INTERRUPTED = "INTERRUPTED"

    def is_terminal(self) -> bool:
        return self in {
            RunLifecycle.COMPLETED,
            RunLifecycle.PARTIAL,
            RunLifecycle.FAILED,
            RunLifecycle.STOPPED,
            RunLifecycle.CANCELLED,
            RunLifecycle.TIMED_OUT,
            RunLifecycle.INTERRUPTED,
        }

    def is_waiting(self) -> bool:
        return self.name.startswith("WAITING")


class RunPhase(StrEnum):
    COMPILE = "COMPILE"
    PLAN = "PLAN"
    ACT = "ACT"
    VERIFY = "VERIFY"


class RouteType(StrEnum):
    CHAT = "CHAT"
    FAST = "FAST"
    MULTI_AGENT = "MULTI_AGENT"
    CLARIFY = "CLARIFY"
    REJECT = "REJECT"

    def is_complex_agent(self) -> bool:
        return self == RouteType.MULTI_AGENT


class AgentRole(StrEnum):
    MAIN = "MAIN"
    PLANNER = "PLANNER"
    REVIEWER = "REVIEWER"


class ReviewDecision(StrEnum):
    PASS = "PASS"
    REVISE = "REVISE"
    REJECT = "REJECT"


class ExecutionStatus(StrEnum):
    PREPARED = "PREPARED"
    DISPATCHED = "DISPATCHED"
    ACKED = "ACKED"
    APPLIED = "APPLIED"
    NOT_APPLIED = "NOT_APPLIED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


class VerificationStatus(StrEnum):
    PENDING = "PENDING"
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    UNKNOWN = "UNKNOWN"


class Attribution(StrEnum):
    THIS_ACTION = "THIS_ACTION"
    EXTERNAL = "EXTERNAL"
    UNKNOWN = "UNKNOWN"


class GoalOutcome(StrEnum):
    SATISFIED = "SATISFIED"
    PARTIAL = "PARTIAL"
    UNSATISFIED = "UNSATISFIED"
    UNKNOWN = "UNKNOWN"


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"


class ChangeSource(StrEnum):
    THIS_TASK = "THIS_TASK"
    EXTERNAL_OPERATOR = "EXTERNAL_OPERATOR"
    SIMULATOR_INTERNAL = "SIMULATOR_INTERNAL"
    UNKNOWN = "UNKNOWN"


class DeviceDomain(StrEnum):
    CABIN = "CABIN"
    MEDIA = "MEDIA"
    NAVIGATION = "NAVIGATION"
    LIFE = "LIFE"
    IOT = "IOT"


class MutableModel(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class Criterion(MutableModel):
    criterion_id: str = ""
    template_id: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    required: bool = True
    source_ref: str | None = None
    bound_at: datetime | None = None
    bound_goal_version: int = 1
    baseline_observation: dict[str, Any] = Field(default_factory=dict)


class DeviceTask(MutableModel):
    run_id: str | None = None
    goal_version: int = 1
    raw_text: str | None = None
    defaults_rule_id: str = "demo-defaults-v1"
    goals: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    criteria: list[Criterion] = Field(default_factory=list)
    binding_context: dict[str, Any] = Field(default_factory=dict)


class Budget(MutableModel):
    deadline: datetime | None = None
    max_model_calls: int = 12
    max_tool_calls: int = 24
    max_write_actions: int = 6
    max_replans: int = 2
    max_same_failure: int = 2
    model_calls: int = 0
    tool_calls: int = 0
    write_actions: int = 0
    replans: int = 0
    same_failure: int = 0

    def expired(self) -> bool:
        return self.deadline is not None and utcnow() > self.deadline

    def count_model(self) -> None:
        if self.expired() or self.model_calls >= self.max_model_calls:
            raise RuntimeError("BUDGET_EXHAUSTED_MODEL")
        self.model_calls += 1

    def count_tool(self) -> None:
        if self.expired() or self.tool_calls >= self.max_tool_calls:
            raise RuntimeError("BUDGET_EXHAUSTED_TOOL")
        self.tool_calls += 1

    def count_write(self) -> None:
        if self.expired() or self.write_actions >= self.max_write_actions:
            raise RuntimeError("BUDGET_EXHAUSTED_WRITE")
        self.write_actions += 1

    def count_replan(self) -> None:
        self.replans += 1
        if self.expired() or self.replans > self.max_replans:
            raise RuntimeError("BUDGET_EXHAUSTED_REPLAN")

    def count_same_failure(self) -> None:
        self.same_failure += 1
        if self.expired() or self.same_failure > self.max_same_failure:
            raise RuntimeError("BUDGET_EXHAUSTED_SAME_FAILURE")

    def reset_same_failure(self) -> None:
        self.same_failure = 0

    def to_map(self) -> dict[str, Any]:
        # Keep Java camelCase keys for API/frontend compatibility.
        return {
            "deadline": self.deadline,
            "modelCalls": self.model_calls,
            "maxModelCalls": self.max_model_calls,
            "toolCalls": self.tool_calls,
            "maxToolCalls": self.max_tool_calls,
            "writeActions": self.write_actions,
            "maxWriteActions": self.max_write_actions,
            "replans": self.replans,
            "maxReplans": self.max_replans,
            "sameFailure": self.same_failure,
            "maxSameFailure": self.max_same_failure,
        }


class StateSnapshot(MutableModel):
    revision: int = 0
    origins: dict[str, dict[str, Any]] = Field(default_factory=dict)
    device_id: str | None = None
    environment_id: str | None = None
    domain_revisions: dict[str, int] = Field(default_factory=dict)
    observed_at: datetime | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    change_source: ChangeSource = ChangeSource.UNKNOWN
    action_id: str | None = None


class ToolAction(MutableModel):
    action_id: str | None = None
    idempotency_key: str | None = None
    run_id: str | None = None
    goal_version: int = 1
    environment_id: str | None = None
    capability_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    expected_revisions: dict[str, int] = Field(default_factory=dict)
    prepared_at: datetime | None = None
    dispatched_at: datetime | None = None
    finished_at: datetime | None = None
    deadline: datetime | None = None
    execution_status: ExecutionStatus = ExecutionStatus.PREPARED
    verification_status: VerificationStatus | None = None
    attribution: Attribution = Attribution.UNKNOWN
    retry_of: str | None = None
    message: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class RuntimeEvent(MutableModel):
    environment_id: str | None = None
    run_id: str | None = None
    seq: int = 0
    at: datetime = Field(default_factory=utcnow)
    goal_version: int | None = None
    action_id: str | None = None
    type: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def of(cls, type_: str, payload: dict[str, Any] | None = None) -> RuntimeEvent:
        return cls(type=type_, at=utcnow(), payload=dict(payload or {}))


class PendingInteraction(MutableModel):
    pending_id: str | None = None
    kind: str | None = None  # CLARIFICATION | CONFIRMATION
    question: str | None = None
    goal_version: int = 1
    capability_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    deadline: datetime | None = None


class RunRecord(MutableModel):
    run_id: str | None = None
    request_id: str | None = None
    device_id: str | None = None
    environment_id: str | None = None
    session_id: str | None = None
    lifecycle: RunLifecycle = RunLifecycle.RECEIVED
    phase: RunPhase = RunPhase.COMPILE
    route_type: RouteType | None = None
    stop_reason: str | None = None
    result_summary: str | None = None
    goal_outcome: GoalOutcome | None = None
    task: DeviceTask = Field(default_factory=DeviceTask)
    budget: Budget = Field(default_factory=Budget)
    actions: list[ToolAction] = Field(default_factory=list)
    events: list[RuntimeEvent] = Field(default_factory=list)
    evaluation_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    cancel_accepted: bool = False
    in_flight_action_id: str | None = None
    unresolved_unknown: bool = False
    pending: PendingInteraction | None = None

    def is_terminal(self) -> bool:
        return self.lifecycle.is_terminal()

    def touch(self) -> None:
        self.updated_at = utcnow()


class TaskSpec(MutableModel):
    goal: str | None = None
    goals: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    context_refs: list[dict[str, Any]] = Field(default_factory=list)
    success_criteria: list[dict[str, Any]] = Field(default_factory=list)
    allowed_capabilities: list[str] = Field(default_factory=list)
    goal_version: int = 1
    run_id: str | None = None
    model_id: str | None = None
    prompt_version: str = "taskspec-v1"

    def to_map(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "goals": self.goals,
            "constraints": self.constraints,
            "context_refs": self.context_refs,
            "success_criteria": self.success_criteria,
            "allowed_capabilities": self.allowed_capabilities,
            "goal_version": self.goal_version,
            "run_id": self.run_id,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
        }


class PlanDraft(MutableModel):
    actions: list[dict[str, Any]] = Field(default_factory=list)
    order: list[int] = Field(default_factory=list)
    preconditions: list[dict[str, Any]] = Field(default_factory=list)
    expected_effects: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    goal_version: int = 1
    run_id: str | None = None
    agent_role: str = "PLANNER"
    model_id: str | None = None
    prompt_version: str = "plandraft-v1"
    revision_round: int = 0
    raw: dict[str, Any] = Field(default_factory=dict)

    def to_map(self) -> dict[str, Any]:
        m: dict[str, Any] = {
            "actions": self.actions,
            "order": self.order,
            "preconditions": self.preconditions,
            "expected_effects": self.expected_effects,
            "assumptions": self.assumptions,
            "unresolved": self.unresolved,
            "goal_version": self.goal_version,
            "run_id": self.run_id,
            "agent_role": self.agent_role,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "revision_round": self.revision_round,
        }
        if self.raw:
            m["raw"] = self.raw
        return m


class ReviewResult(MutableModel):
    decision: ReviewDecision = ReviewDecision.REJECT
    missing_goals: list[str] = Field(default_factory=list)
    violated_constraints: list[str] = Field(default_factory=list)
    risky_actions: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    goal_version: int = 1
    run_id: str | None = None
    agent_role: str = "REVIEWER"
    model_id: str | None = None
    prompt_version: str = "review-v1"
    raw: dict[str, Any] = Field(default_factory=dict)

    def to_map(self) -> dict[str, Any]:
        m: dict[str, Any] = {
            "decision": self.decision.value if self.decision else None,
            "missing_goals": self.missing_goals,
            "violated_constraints": self.violated_constraints,
            "risky_actions": self.risky_actions,
            "evidence_gaps": self.evidence_gaps,
            "suggestions": self.suggestions,
            "goal_version": self.goal_version,
            "run_id": self.run_id,
            "agent_role": self.agent_role,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
        }
        if self.raw:
            m["raw"] = self.raw
        return m


class CompiledTaskCandidate(MutableModel):
    route_hint: str | None = None
    clarify_question: str | None = None
    reject_reason: str | None = None
    goals: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    criteria: list[dict[str, Any]] = Field(default_factory=list)
    fast_action: dict[str, Any] | None = None
    summary: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RouterDecision(MutableModel):
    route: RouteType
    agent_role: str = "MAIN"
    direct_action: dict[str, Any] | None = None
    summary: str = ""
