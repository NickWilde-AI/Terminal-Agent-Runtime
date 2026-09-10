"""Runtime settings, model contracts, task binding and multi-agent helpers."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel

from terminal_agent.capability.core import CapabilityRegistry, expected_effects
from terminal_agent.contracts import (
    AgentRole,
    CompiledTaskCandidate,
    Criterion,
    DeviceTask,
    PlanDraft,
    ReviewDecision,
    ReviewResult,
    StateSnapshot,
    TaskSpec,
    now,
)
from terminal_agent.runtime.task_binder import action_for as shared_action_for
from terminal_agent.runtime.task_binder import action_params as shared_action_params


class BudgetSettings(BaseModel):
    absolute_deadline_seconds: int = 120
    max_model_calls: int = 12
    max_tool_calls: int = 24
    max_write_actions: int = 6
    max_replans: int = 2
    max_same_failure: int = 2


class RuntimeSettings(BaseModel):
    defaults_rule_id: str = "demo-defaults-v1"
    fresh_window_ms: int = 2000
    budget: BudgetSettings = BudgetSettings()


class ModelPort(Protocol):
    def mode(self) -> str: ...
    async def compile_task(
        self, user_text: str, observation: StateSnapshot, memory_hints: list[dict[str, Any]]
    ) -> CompiledTaskCandidate: ...
    async def plan_next(
        self,
        run_id: str,
        goals: list[dict[str, Any]],
        constraints: list[dict[str, Any]],
        criteria: list[dict[str, Any]],
        observation: StateSnapshot,
        prior_actions: list[dict[str, Any]],
        memory_hints: list[dict[str, Any]],
    ) -> dict[str, Any]: ...
    async def plan_draft(
        self,
        run_id: str,
        task_spec: TaskSpec,
        observation: StateSnapshot,
        prior_actions: list[dict[str, Any]],
        revise_suggestions: list[str],
        revision_round: int,
    ) -> PlanDraft: ...
    async def review_plan(self, run_id: str, task_spec: TaskSpec, draft: PlanDraft) -> ReviewResult: ...
    async def request_context(
        self,
        run_id: str,
        goal_version: int,
        deadline: Any,
        role: AgentRole = AgentRole.MAIN,
    ) -> None: ...
    async def feedback(self, run_id: str, goal_version: int, plan: dict[str, Any], result: dict[str, Any]) -> None: ...


class ModelRouter:
    def __init__(
        self, model_id: str = "step-3.5-flash", edge_model_id: str = "step-edge-stub", placement: str = "cloud"
    ) -> None:
        self.model_id, self.edge_model_id, self._placement, self._epoch = model_id, edge_model_id, placement.lower(), 1

    @property
    def epoch(self) -> int:
        return self._epoch

    @property
    def placement(self) -> str:
        return self._placement or "cloud"

    @property
    def active_model_id(self) -> str:
        return self.edge_model_id if self.placement == "edge" else self.model_id

    @property
    def is_offline_edge(self) -> bool:
        return self.placement == "edge"

    def set_placement(self, placement: str | None) -> None:
        next_ = (placement or "cloud").lower()
        if next_ != self.placement:
            self._epoch += 1
        self._placement = next_


class NullMemory:
    async def compile_hints(self, session_id: str, text: str, snapshot: StateSnapshot) -> list[dict[str, Any]]:
        return []

    async def plan_hints(
        self,
        session_id: str,
        text: str | None,
        goals: list[dict[str, Any]],
        constraints: list[dict[str, Any]],
        snapshot: StateSnapshot,
        prior: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return []


class TaskBinder:
    """Product-owned criteria binder. TODO: goal compilation remains owned by goal_compiler."""

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self.registry = registry or CapabilityRegistry()

    def bind(self, run_id: str, text: str, defaults: str, candidate: CompiledTaskCandidate) -> DeviceTask:
        task = DeviceTask(
            run_id=run_id,
            raw_text=text,
            defaults_rule_id=defaults,
            goals=list(candidate.goals),
            constraints=list(candidate.constraints),
        )
        for goal in task.goals:
            action = self.action_for(goal)
            if action is None:
                if goal.get("type") in ("nav_diagnostic", "media_keep_muted"):
                    continue
                raise ValueError(f"未注册目标类型: {goal.get('type')}")
            cap = self.registry.canonical(str(action["capability_id"]))
            params = self.params(action)
            validation = self.registry.validate(cap, params)
            if not validation.ok:
                raise ValueError(validation.message)
            expected = expected_effects(cap, params)
            if expected:
                for field, value in expected.items():
                    self._add(task, "field_eq", {"field": field, "value": value}, str(goal.get("source", "user")))
            else:
                special = {
                    "navigation.add_waypoint": ("nav_waypoint_contains", {"name": params.get("name")}),
                    "navigation.remove_waypoint": ("nav_waypoint_absent", {"name": params.get("name")}),
                    "navigation.query_eta": ("nav_query_type", {"type": "eta"}),
                    "navigation.query_status": ("nav_query_type", {"type": "status"}),
                    "navigation.query_waypoints": ("nav_query_type", {"type": "waypoints"}),
                }.get(cap)
                if not special:
                    raise ValueError(f"无法为能力生成验收条件: {cap}")
                self._add(task, special[0], special[1], str(goal.get("source", "user")))
            if cap == "navigation.add_waypoint" and goal.get("retain_destination") is not None:
                self._add(
                    task, "field_eq", {"field": "navigation_destination", "value": goal["retain_destination"]}, "user"
                )
        for constraint in task.constraints:
            if constraint.get("type") == "keep_navigation_prompt":
                self._add(task, "nav_prompt_retained", {"min_volume": constraint.get("min_volume", 1)}, "user")
        if any(c.get("template_id") == "nav_prompt_event_played" for c in candidate.criteria):
            self._add(task, "nav_prompt_event_played", {}, "diagnostic contract")
        if not task.criteria:
            raise ValueError("没有可验收目标，需澄清")
        task.binding_context["summary"] = candidate.summary
        return task

    @staticmethod
    def _add(task: DeviceTask, template: str, params: dict[str, Any], source: str) -> None:
        task.criteria.append(
            Criterion(
                criterion_id=f"c{len(task.criteria) + 1}",
                template_id=template,
                params=params,
                source_ref=source,
                bound_at=now(),
                bound_goal_version=task.goal_version,
            )
        )

    @staticmethod
    def params(action: dict[str, Any]) -> dict[str, Any]:
        return shared_action_params(action)

    @staticmethod
    def action_for(goal: dict[str, Any]) -> dict[str, Any] | None:
        return shared_action_for(goal)


def task_spec_from(task: DeviceTask, run_id: str, model_id: str) -> TaskSpec:
    allowed = []
    for goal in task.goals:
        action = TaskBinder.action_for(goal)
        if action and action["capability_id"] not in allowed:
            allowed.append(str(action["capability_id"]))
    return TaskSpec(
        run_id=run_id,
        model_id=model_id,
        goal_version=task.goal_version,
        goal=str(task.binding_context.get("summary", task.raw_text)),
        goals=list(task.goals),
        constraints=list(task.constraints),
        success_criteria=[
            {"template_id": c.template_id, "params": c.params, "required": c.required} for c in task.criteria
        ],
        allowed_capabilities=allowed,
    )


def review_plan(spec: TaskSpec, draft: PlanDraft, model_id: str | None = None) -> ReviewResult:
    result = ReviewResult(run_id=spec.run_id, goal_version=spec.goal_version, model_id=model_id)
    constraints = {str(c.get("type")) for c in spec.constraints}
    for action in draft.actions:
        cap = str(action.get("capability_id"))
        if "no_cabin_write" in constraints and cap.startswith("climate."):
            result.violated_constraints.append(f"no_cabin_write vs {cap}")
        if "no_window" in constraints and cap.startswith("window."):
            result.violated_constraints.append(f"no_window vs {cap}")
        if "no_media_write" in constraints and cap.startswith("media."):
            result.violated_constraints.append(f"no_media_write vs {cap}")
    if result.violated_constraints:
        result.decision = ReviewDecision.REJECT
        result.suggestions.append("移除违规动作后重试")
    else:
        result.decision = ReviewDecision.PASS
    return result
