"""Runtime contracts shared by the harness, adapters and persistence layer."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def now() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class RuntimeModel(BaseModel):
    model_config = ConfigDict(use_enum_values=False, validate_assignment=True, extra="ignore")


class DeviceDomain(StrEnum):
    CABIN = "CABIN"
    MEDIA = "MEDIA"
    NAVIGATION = "NAVIGATION"
    AUDIO = "AUDIO"
    LIFE = "LIFE"
    IOT = "IOT"


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


class RunPhase(StrEnum):
    COMPILE = "COMPILE"
    PLAN = "PLAN"
    ACT = "ACT"
    WAIT = "WAIT"
    FINISH = "FINISH"


class RouteType(StrEnum):
    FAST = "FAST"
    MULTI_AGENT = "MULTI_AGENT"
    AGENT = "AGENT"
    CHAT = "CHAT"
    CLARIFY = "CLARIFY"
    REJECT = "REJECT"

    def is_complex_agent(self) -> bool:
        return self in (RouteType.MULTI_AGENT, RouteType.AGENT)


class ExecutionStatus(StrEnum):
    PREPARED = "PREPARED"
    PROPOSED = "PROPOSED"
    AUTHORIZED = "AUTHORIZED"
    DISPATCHED = "DISPATCHED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    APPLIED = "APPLIED"
    NOT_APPLIED = "NOT_APPLIED"
    UNKNOWN = "UNKNOWN"
    REJECTED = "REJECTED"
    CANCELLED_BEFORE_DISPATCH = "CANCELLED_BEFORE_DISPATCH"


class VerificationStatus(StrEnum):
    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class Attribution(StrEnum):
    THIS_ACTION = "THIS_ACTION"
    EXTERNAL = "EXTERNAL"
    UNKNOWN = "UNKNOWN"


class GoalOutcome(StrEnum):
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"
    UNKNOWN = "UNKNOWN"


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"


class ReviewDecision(StrEnum):
    PASS = "PASS"
    REVISE = "REVISE"
    REJECT = "REJECT"


class AgentRole(StrEnum):
    MAIN = "MAIN"
    PLANNER = "PLANNER"
    REVIEWER = "REVIEWER"


class ChangeSource(StrEnum):
    THIS_TASK = "THIS_TASK"
    EXTERNAL_OPERATOR = "EXTERNAL_OPERATOR"
    SIMULATOR_INTERNAL = "SIMULATOR_INTERNAL"
    UNKNOWN = "UNKNOWN"


class StateSnapshot(RuntimeModel):
    revision: int = 0
    origins: dict[str, dict[str, Any]] = Field(default_factory=dict)
    device_id: str | None = None
    environment_id: str | None = None
    domain_revisions: dict[str, int] = Field(default_factory=dict)
    observed_at: datetime | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    change_source: str = "UNKNOWN"
    action_id: str | None = None


class ActionRecord(RuntimeModel):
    action_id: str
    idempotency_key: str
    capability_id: str
    environment_id: str
    run_id: str | None = None
    status: str = "QUEUED"
    message: str | None = None
    goal_version: int = 0
    params: dict[str, Any] = Field(default_factory=dict)
    expected_revisions: dict[str, int] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=now)
    finished_at: datetime | None = None
    deadline: datetime | None = None
    apply_after_ms: int = 0
    revision: int = 0


class Criterion(RuntimeModel):
    criterion_id: str = Field(default_factory=lambda: new_id("criterion"))
    template_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    required: bool = True
    source_ref: str | None = None
    baseline_observation: dict[str, Any] = Field(default_factory=dict)
    bound_goal_version: int = 0
    bound_at: datetime | None = None


class DeviceTask(RuntimeModel):
    run_id: str | None = None
    goal_version: int = 1
    raw_text: str | None = None
    defaults_rule_id: str = "demo-defaults-v1"
    goals: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    criteria: list[Criterion] = Field(default_factory=list)
    binding_context: dict[str, Any] = Field(default_factory=dict)


class Budget(RuntimeModel):
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
        return self.deadline is not None and now() > self.deadline

    def _count(self, field: str, maximum: str, code: str, preincrement: bool = False) -> None:
        value = getattr(self, field)
        if self.expired() or (value + 1 > getattr(self, maximum) if preincrement else value >= getattr(self, maximum)):
            raise RuntimeError(code)
        setattr(self, field, value + 1)

    def count_model(self) -> None:
        self._count("model_calls", "max_model_calls", "BUDGET_EXHAUSTED_MODEL")

    def count_tool(self) -> None:
        self._count("tool_calls", "max_tool_calls", "BUDGET_EXHAUSTED_TOOL")

    def count_write(self) -> None:
        self._count("write_actions", "max_write_actions", "BUDGET_EXHAUSTED_WRITE")

    def count_replan(self) -> None:
        self._count("replans", "max_replans", "BUDGET_EXHAUSTED_REPLAN", True)

    def count_same_failure(self) -> None:
        self._count("same_failure", "max_same_failure", "BUDGET_EXHAUSTED_SAME_FAILURE", True)

    def reset_same_failure(self) -> None:
        self.same_failure = 0

    def to_map(self) -> dict[str, Any]:
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


class ToolAction(RuntimeModel):
    action_id: str
    idempotency_key: str
    run_id: str
    goal_version: int
    environment_id: str
    capability_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    expected_revisions: dict[str, int] = Field(default_factory=dict)
    prepared_at: datetime = Field(default_factory=now)
    dispatched_at: datetime | None = None
    finished_at: datetime | None = None
    deadline: datetime | None = None
    execution_status: ExecutionStatus = ExecutionStatus.PREPARED
    verification_status: VerificationStatus | None = None
    attribution: Attribution = Attribution.UNKNOWN
    retry_of: str | None = None
    message: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class PendingInteraction(RuntimeModel):
    pending_id: str = Field(default_factory=lambda: new_id("pending"))
    type: str
    goal_version: int
    capability_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    question: str | None = None
    expires_at: datetime
    source_message_id: str | None = None

    def to_map(self) -> dict[str, Any]:
        return {
            "pending_id": self.pending_id,
            "pendingId": self.pending_id,
            "type": self.type,
            "goal_version": self.goal_version,
            "goalVersion": self.goal_version,
            "capability_id": self.capability_id,
            "capabilityId": self.capability_id,
            "params": self.params,
            "question": self.question,
            "expires_at": self.expires_at,
            "expiresAt": self.expires_at,
        }


class RuntimeEvent(RuntimeModel):
    environment_id: str | None = None
    run_id: str | None = None
    seq: int = 0
    at: datetime = Field(default_factory=now)
    goal_version: int | None = None
    action_id: str | None = None
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RunRecord(RuntimeModel):
    run_id: str
    request_id: str
    device_id: str
    environment_id: str
    session_id: str = "local"
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
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    cancel_accepted: bool = False
    in_flight_action_id: str | None = None
    unresolved_unknown: bool = False
    pending: PendingInteraction | None = None

    def is_terminal(self) -> bool:
        return self.lifecycle in {
            RunLifecycle.COMPLETED,
            RunLifecycle.PARTIAL,
            RunLifecycle.FAILED,
            RunLifecycle.STOPPED,
            RunLifecycle.CANCELLED,
            RunLifecycle.TIMED_OUT,
            RunLifecycle.INTERRUPTED,
        }

    def touch(self) -> None:
        self.updated_at = now()


class CompiledTaskCandidate(RuntimeModel):
    route_hint: str | None = None
    clarify_question: str | None = None
    reject_reason: str | None = None
    goals: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    criteria: list[dict[str, Any]] = Field(default_factory=list)
    fast_action: dict[str, Any] | None = None
    summary: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class TaskSpec(RuntimeModel):
    goal: str | None = None
    goals: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    context_refs: list[dict[str, Any]] = Field(default_factory=list)
    success_criteria: list[dict[str, Any]] = Field(default_factory=list)
    allowed_capabilities: list[str] = Field(default_factory=list)
    goal_version: int = 0
    run_id: str | None = None
    model_id: str | None = None
    prompt_version: str = "taskspec-v1"

    def to_map(self) -> dict[str, Any]:
        return self.model_dump()


class PlanDraft(RuntimeModel):
    actions: list[dict[str, Any]] = Field(default_factory=list)
    order: list[int] = Field(default_factory=list)
    preconditions: list[dict[str, Any]] = Field(default_factory=list)
    expected_effects: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    goal_version: int = 0
    run_id: str | None = None
    agent_role: str = "PLANNER"
    model_id: str | None = None
    prompt_version: str = "plandraft-v1"
    revision_round: int = 0
    raw: dict[str, Any] = Field(default_factory=dict)

    def to_map(self) -> dict[str, Any]:
        return self.model_dump(exclude={"raw"} if not self.raw else set())


class ReviewResult(RuntimeModel):
    decision: ReviewDecision = ReviewDecision.REJECT
    missing_goals: list[str] = Field(default_factory=list)
    violated_constraints: list[str] = Field(default_factory=list)
    risky_actions: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    goal_version: int = 0
    run_id: str | None = None
    agent_role: str = "REVIEWER"
    model_id: str | None = None
    prompt_version: str = "review-v1"
    raw: dict[str, Any] = Field(default_factory=dict)

    def to_map(self) -> dict[str, Any]:
        return self.model_dump(exclude={"raw"} if not self.raw else set())


class RouterDecision(RuntimeModel):
    route: RouteType
    agent_role: str = "MAIN"
    direct_action: dict[str, Any] | None = None
    summary: str = ""


# Compatibility aliases for older import paths (agent.contracts / domain.models).
MutableModel = RuntimeModel
utcnow = now


def dict_of(**kwargs: Any) -> dict[str, Any]:
    """Preserve insertion order; allow None values."""
    return dict(kwargs)
