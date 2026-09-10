"""Deterministic model used by local demos and evaluation."""

from __future__ import annotations

from typing import Any

from terminal_agent.agent.contracts import CompiledTaskCandidate, PlanDraft, ReviewResult, TaskSpec
from terminal_agent.domain.models import StateSnapshot
from terminal_agent.model.normalizer import ModelOutputNormalizer


class FakeModelAdapter:
    def mode(self) -> str:
        return "fake"

    def compile_task(
        self, user_text: str, observation: StateSnapshot | None,
        memory_hints: list[dict[str, Any]] | None = None,
    ) -> CompiledTaskCandidate:
        # Intentionally delegates exactly as Java does; imported lazily to avoid a package cycle.
        from terminal_agent.runtime.goal_compiler import GoalCompiler

        candidate = GoalCompiler.compile(user_text, observation, memory_hints or [])
        candidate.raw.update(model_mode="fake", agent_role="MAIN")
        ModelOutputNormalizer.normalize(candidate, user_text)
        return candidate

    def plan_draft(
        self, run_id: str, task_spec: TaskSpec, observation: StateSnapshot,
        prior_actions: list[dict[str, Any]], revise_suggestions: list[str] | None,
        revision_round: int,
    ) -> PlanDraft:
        from terminal_agent.agent.multi_agent import MultiAgentSupport

        draft = MultiAgentSupport.build_plan_draft(
            task_spec, observation, prior_actions, revision_round, "fake"
        )
        draft.run_id = run_id
        draft.raw.update(agent_role="PLANNER", revise_suggestions=revise_suggestions or [])
        return draft

    def review_plan(self, run_id: str, task_spec: TaskSpec, draft: PlanDraft) -> ReviewResult:
        from terminal_agent.agent.multi_agent import MultiAgentSupport

        result = MultiAgentSupport.review(task_spec, draft, "fake")
        result.run_id = run_id
        result.raw["agent_role"] = "REVIEWER"
        return result

    def plan_next(
        self, run_id: str, goals: list[dict[str, Any]], constraints: list[dict[str, Any]],
        criteria: list[dict[str, Any]], observation: StateSnapshot,
        prior_actions: list[dict[str, Any]], memory_hints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from terminal_agent.agent.multi_agent import MultiAgentSupport
        from terminal_agent.runtime.support import TaskBinder

        allowed = []
        for goal in goals or []:
            action = TaskBinder.action_for(goal)
            if action:
                allowed.append(str(action["capability_id"]))
        spec = TaskSpec(run_id=run_id, goals=goals or [], constraints=constraints or [],
                        allowed_capabilities=allowed)
        draft = MultiAgentSupport.build_plan_draft(spec, observation, prior_actions, 0, "fake")
        if not draft.actions:
            reason = draft.assumptions[0] if draft.assumptions else "观察显示目标已满足或无需动作"
            return {"decision": "FINISH", "reason": reason}
        return {**draft.actions[0], "decision": "ACT"}

    def request_context(self, *_: Any, **__: Any) -> None:
        return None

    def feedback(self, *_: Any, **__: Any) -> None:
        return None
