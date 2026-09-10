"""Single-shot deterministic baseline runner (not iterative function calling)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from terminal_agent.contracts import (
    DeviceDomain,
    ExecutionStatus,
    GoalOutcome,
    RouteType,
    RunLifecycle,
    RunPhase,
    RunRecord,
    new_id,
    now,
)
from terminal_agent.device.simulator import DeviceSimulator
from terminal_agent.persistence.sqlite import SqlitePersistence
from terminal_agent.persistence.store import InMemoryRunStore
from terminal_agent.runtime.executor import CapabilityExecutor
from terminal_agent.runtime.support import ModelPort, RuntimeSettings, TaskBinder
from terminal_agent.runtime.verifier import Verifier


async def _maybe_await(value: Any) -> Any:
    import inspect

    return await value if inspect.isawaitable(value) else value


class BaselineRunner:
    def __init__(
        self,
        store: InMemoryRunStore,
        simulator: DeviceSimulator,
        model: ModelPort,
        binder: TaskBinder,
        executor: CapabilityExecutor,
        verifier: Verifier,
        persistence: SqlitePersistence,
        settings: RuntimeSettings | None = None,
    ) -> None:
        self.store, self.simulator, self.model, self.binder = store, simulator, model, binder
        self.executor, self.verifier, self.persistence = executor, verifier, persistence
        self.settings = settings or RuntimeSettings()

    async def run(self, request_id: str | None, text: str) -> RunRecord:
        b = self.settings.budget
        run = RunRecord(
            run_id=new_id("base"),
            request_id=request_id or new_id("req"),
            device_id=self.simulator.device_id,
            environment_id=self.simulator.environment_id,
            session_id="baseline",
            lifecycle=RunLifecycle.RUNNING,
            phase=RunPhase.COMPILE,
        )
        run.budget.deadline = now() + timedelta(seconds=b.absolute_deadline_seconds)
        run.budget.max_model_calls, run.budget.max_tool_calls = b.max_model_calls, b.max_tool_calls
        run.budget.max_write_actions = b.max_write_actions
        self.store.save(run)
        await self.store.append_event(
            run, "RUN_RECEIVED", {"text": text, "mode": "baseline", "model_mode": self.model.mode()}
        )
        observation = await self.executor.read(run, set(DeviceDomain))
        run.budget.count_model()
        candidate = await _maybe_await(self.model.compile_task(text, observation, []))
        await self.store.append_event(run, "COMPILE", {"routeHint": candidate.route_hint, "summary": candidate.summary})
        route = {
            "FAST": RouteType.FAST,
            "AGENT": RouteType.MULTI_AGENT,
            "MULTI_AGENT": RouteType.MULTI_AGENT,
            "CHAT": RouteType.CHAT,
            "REJECT": RouteType.REJECT,
        }.get((candidate.route_hint or "").upper(), RouteType.CLARIFY)
        run.route_type = route
        if route == RouteType.REJECT:
            await self._finish(
                run, RunLifecycle.STOPPED, "UNSUPPORTED", candidate.reject_reason, GoalOutcome.UNSATISFIED
            )
            return run
        if route == RouteType.CLARIFY:
            run.lifecycle, run.result_summary = RunLifecycle.WAITING_CLARIFICATION, candidate.clarify_question
            await self.persistence.persist_run(run)
            return run
        run.task = self.binder.bind(run.run_id, text, self.settings.defaults_rule_id, candidate)
        if route == RouteType.FAST and candidate.fast_action:
            action = await self.executor.execute_write(
                run, str(candidate.fast_action["capability_id"]), self.binder.params(candidate.fast_action)
            )
            await self._conclude(run)
            return run
        await self.store.append_event(
            run,
            "BASELINE_PLAN",
            {"mode": "single_shot_deterministic_from_goals", "note": "不回传工具结果；非纯 FC，是编译目标的确定性展开"},
        )
        steps = []
        no_cabin = any(c.get("type") == "no_cabin_write" for c in run.task.constraints)
        for goal in run.task.goals:
            type_ = goal.get("type")
            if type_ == "cabin_temperature" and not no_cabin:
                steps.append(("cabin.set_temperature", {"value": goal.get("value")}))
            elif type_ == "cabin_fan" and not no_cabin:
                steps.append(("cabin.set_fan", {"value": goal.get("value")}))
            elif type_ == "media_volume" and not observation.state.get("media_muted"):
                steps.append(("media.set_volume", {"value": goal.get("value")}))
            elif type_ == "nav_muted":
                steps.append(("navigation.set_muted", {"value": goal.get("value")}))
            elif type_ == "nav_prompt_enabled":
                steps.append(("navigation.set_prompt_enabled", {"value": goal.get("value")}))
            elif type_ == "nav_volume":
                steps.append(("navigation.set_volume", {"value": goal.get("value")}))
        unique = {cap: params for cap, params in steps}
        for cap, params in unique.items():
            if run.cancel_accepted or run.is_terminal():
                break
            action = await self.executor.execute_write(run, cap, params)
            if action.execution_status == ExecutionStatus.UNKNOWN:
                await self._finish(run, RunLifecycle.STOPPED, "UNRESOLVED_ACTION", "未知动作", GoalOutcome.UNKNOWN)
                return run
        if any(c.template_id == "nav_prompt_event_played" for c in run.task.criteria):
            await self.simulator.emit_prompt_event()
        await self._conclude(run)
        return run

    async def _conclude(self, run: RunRecord) -> None:
        result = await self.verifier.verify_task(run)
        run.evaluation_snapshot["details"] = result.details
        if result.outcome == GoalOutcome.SATISFIED:
            await self._finish(run, RunLifecycle.COMPLETED, None, result.summary, result.outcome)
        elif result.outcome == GoalOutcome.UNKNOWN:
            await self._finish(run, RunLifecycle.STOPPED, "UNKNOWN_OUTCOME", result.summary, result.outcome)
        else:
            partial = any(d["status"] == "SATISFIED" for d in result.details)
            await self._finish(
                run,
                RunLifecycle.PARTIAL if partial else RunLifecycle.FAILED,
                "PARTIAL" if partial else "UNSATISFIED",
                result.summary,
                result.outcome,
            )

    async def _finish(
        self,
        run: RunRecord,
        lifecycle: RunLifecycle,
        stop: str | None,
        summary: str | None,
        outcome: GoalOutcome,
    ) -> None:
        if run.is_terminal():
            return
        run.lifecycle, run.phase, run.stop_reason = lifecycle, RunPhase.FINISH, stop
        run.result_summary, run.goal_outcome = summary, outcome
        await self.store.append_event(run, "RUN_FINISHED", {"lifecycle": lifecycle.value, "mode": "baseline"})
        await self.persistence.persist_run(run)
