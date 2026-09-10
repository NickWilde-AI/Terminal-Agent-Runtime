"""ModelPort protocol shared by fake, cloud, and edge placements."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from terminal_agent.agent.contracts import CompiledTaskCandidate, PlanDraft, ReviewResult, TaskSpec
from terminal_agent.domain.models import AgentRole, StateSnapshot


class ModelPort(Protocol):
    def mode(self) -> str: ...

    def compile_task(
        self, user_text: str, observation: StateSnapshot | None,
        memory_hints: list[dict[str, Any]] | None = None,
    ) -> CompiledTaskCandidate: ...

    def plan_next(
        self, run_id: str, goals: list[dict[str, Any]], constraints: list[dict[str, Any]],
        criteria: list[dict[str, Any]], observation: StateSnapshot,
        prior_actions: list[dict[str, Any]], memory_hints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    def plan_draft(
        self, run_id: str, task_spec: TaskSpec, observation: StateSnapshot,
        prior_actions: list[dict[str, Any]], revise_suggestions: list[str] | None,
        revision_round: int,
    ) -> PlanDraft: ...

    def review_plan(self, run_id: str, task_spec: TaskSpec, draft: PlanDraft) -> ReviewResult: ...

    def request_context(
        self, run_id: str, goal_version: int, deadline: datetime | None,
        role: AgentRole = AgentRole.MAIN,
    ) -> None: ...

    def feedback(
        self, run_id: str, goal_version: int, plan: dict[str, Any], result: dict[str, Any],
    ) -> None: ...
