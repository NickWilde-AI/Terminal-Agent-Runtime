"""Async harness preserving the Java runtime's control and safety invariants."""

from __future__ import annotations

import asyncio
import inspect
import re
from copy import deepcopy
from datetime import timedelta
from typing import Any

from terminal_agent.capability.core import effects_match
from terminal_agent.contracts import (
    AgentRole,
    CompiledTaskCandidate,
    DeviceDomain,
    DeviceTask,
    ExecutionStatus,
    GoalOutcome,
    OverallOutcome,
    PendingInteraction,
    PreflightDecision,
    RouteType,
    RunLifecycle,
    RunPhase,
    RunRecord,
    new_id,
    now,
)
from terminal_agent.device.port import DevicePort
from terminal_agent.orchestration.platform import PlatformServices, sanitize_tenant_id
from terminal_agent.persistence.sqlite import SqlitePersistence
from terminal_agent.persistence.store import InMemoryRunStore
from terminal_agent.runtime.executor import CapabilityExecutor
from terminal_agent.runtime.router import ExecutionRouter
from terminal_agent.runtime.support import (
    ModelPort,
    ModelRouter,
    NullMemory,
    RuntimeSettings,
    TaskBinder,
    task_spec_from,
)
from terminal_agent.runtime.auditor import execution_evidence, should_replan, stamp_audit
from terminal_agent.runtime.outcome import OutcomeAggregator
from terminal_agent.runtime.preflight import PreflightGate
from terminal_agent.runtime.verifier import Verifier


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class HarnessService:
    def __init__(
        self,
        store: InMemoryRunStore,
        device: DevicePort,
        model: ModelPort,
        binder: TaskBinder,
        executor: CapabilityExecutor,
        verifier: Verifier,
        persistence: SqlitePersistence,
        settings: RuntimeSettings | None = None,
        memory: Any | None = None,
        router: ModelRouter | None = None,
        platform: PlatformServices | None = None,
    ) -> None:
        self.store, self.device, self.model, self.binder = store, device, model, binder
        self.executor, self.verifier, self.persistence = executor, verifier, persistence
        self.settings, self.memory, self.router = (
            settings or RuntimeSettings(),
            memory or NullMemory(),
            router or ModelRouter(),
        )
        self.platform = platform
        self.preflight = PreflightGate(executor.registry, executor.policy)
        self._running: dict[str, asyncio.Task[None]] = {}
        self._deadlines: dict[str, asyncio.Task[None]] = {}
        self._admission = asyncio.Lock()
        self._eval_pause = False
        self._barrier = asyncio.Event()
        self._barrier.set()
        self._deadline_task: asyncio.Task[None] | None = None

    def arm_eval_pause_after_goal_bound(self) -> None:
        self._eval_pause = True
        self._barrier.clear()

    def release_eval_pause(self) -> None:
        self._eval_pause = False
        self._barrier.set()

    async def await_idle(self, timeout_ms: int) -> None:
        end = asyncio.get_running_loop().time() + timeout_ms / 1000
        while self._running and asyncio.get_running_loop().time() < end:
            await asyncio.sleep(0.02)

    async def create_run(
        self,
        request_id: str | None,
        text: str,
        session: str | None = None,
        wait: bool = True,
        tenant_id: str | None = None,
        trace_id: str | None = None,
        actor: str | None = None,
    ) -> RunRecord:
        if text is None or not text.strip() or len(text) > 4000:
            raise ValueError("请输入1至4000字的任务")
        tenant = sanitize_tenant_id(tenant_id)
        actor_id = (actor or "anonymous").strip()[:64] or "anonymous"
        trace = (trace_id or "").strip() or new_id("tr")
        async with self._admission:
            if request_id:
                old = self.store.find_by_request_id(request_id, tenant)
                if old:
                    original = old.task.binding_context.get("original_request", old.task.raw_text)
                    if original != text or old.session_id != (session or "local") or old.tenant_id != tenant:
                        raise RuntimeError("同 requestId 不同正文")
                    return old
            if self.platform:
                quota_code = self.platform.quota.check(tenant, self.store.active_count(tenant))
                if quota_code:
                    self.platform.metrics.inc("quota_rejected")
                    self.platform.audit.emit(
                        "quota_rejected",
                        tenant_id=tenant,
                        actor=actor_id,
                        result="denied",
                        detail={"code": quota_code},
                    )
                    raise RuntimeError(quota_code)
            if self.store.has_active_write_run(self.device.device_id):
                raise RuntimeError("同设备已有活动任务或未解决 UNKNOWN")
            budget = self.settings.budget
            run = RunRecord(
                run_id=new_id("run"),
                request_id=request_id or new_id("req"),
                device_id=self.device.device_id,
                environment_id=self.device.environment_id,
                session_id=session or "local",
                tenant_id=tenant,
                trace_id=trace,
                actor=actor_id,
            )
            run.task.run_id, run.task.raw_text = run.run_id, text
            run.task.binding_context["original_request"] = text
            run.budget.deadline = now() + timedelta(seconds=budget.absolute_deadline_seconds)
            run.budget.max_model_calls, run.budget.max_tool_calls = budget.max_model_calls, budget.max_tool_calls
            run.budget.max_write_actions, run.budget.max_replans = budget.max_write_actions, budget.max_replans
            run.budget.max_same_failure = budget.max_same_failure
            run.evaluation_snapshot.update(model_mode=self.model.mode(), model_id=self.router.active_model_id)
            self.store.save(run)
            if self.platform:
                self.platform.quota.note_created(tenant)
                self.platform.metrics.inc("runs_created")
                self.platform.audit.emit(
                    "run_created",
                    tenant_id=tenant,
                    actor=actor_id,
                    run_id=run.run_id,
                    detail={"trace_id": trace},
                )
            await self.store.append_event(
                run,
                "RUN_RECEIVED",
                {"text": text, "model_mode": self.model.mode(), "model_id": self.router.active_model_id},
            )
            self._ensure_deadline_timer()
            if hasattr(self.device, "start_clock"):
                self.device.start_clock()
        await self._launch(run, wait)
        return run

    def _ensure_deadline_timer(self) -> None:
        """Poll budget expiry like Java's harness-deadlines scheduler (100ms)."""
        if self._deadline_task and not self._deadline_task.done():
            return

        async def _loop() -> None:
            while True:
                for run in list(self.store.list()):
                    if not run.is_terminal() and run.budget.expired():
                        await self._finish(
                            run,
                            RunLifecycle.TIMED_OUT,
                            "TIMED_OUT",
                            "任务到期，停止新动作；在途动作仍可能生效",
                            GoalOutcome.UNKNOWN,
                        )
                await asyncio.sleep(0.1)

        self._deadline_task = asyncio.create_task(_loop(), name="harness-deadlines")

    async def _watch_deadline(self, run: RunRecord) -> None:
        # Kept for compatibility; global deadline timer is authoritative.
        try:
            while not run.is_terminal():
                if run.budget.expired():
                    await self._finish(
                        run,
                        RunLifecycle.TIMED_OUT,
                        "TIMED_OUT",
                        "任务到期，停止新动作；在途动作仍可能生效",
                        GoalOutcome.UNKNOWN,
                    )
                    return
                await asyncio.sleep(0.1)
        finally:
            self._deadlines.pop(run.run_id, None)

    async def _launch(self, run: RunRecord, wait: bool) -> None:
        if run.run_id in self._running:
            return

        async def job() -> None:
            try:
                await self._work(run)
            except Exception as exc:
                message = str(exc) or type(exc).__name__
                await self._finish(
                    run,
                    RunLifecycle.STOPPED,
                    message if message.startswith("BUDGET") else "EXECUTION_ERROR",
                    f"执行停止：{message}",
                    GoalOutcome.UNKNOWN,
                )
            finally:
                self._running.pop(run.run_id, None)

        task = asyncio.create_task(job(), name=f"harness-{run.run_id}")
        self._running[run.run_id] = task
        if wait:
            await task

    async def _pause(self, run: RunRecord) -> None:
        if not self._eval_pause:
            return
        await self.store.append_event(run, "EVAL_PAUSE", {"at": "GOAL_BOUND"})
        try:
            await asyncio.wait_for(self._barrier.wait(), timeout=30)
        except TimeoutError:
            pass

    async def _work(self, run: RunRecord) -> None:
        if run.is_terminal():
            return
        run.lifecycle = RunLifecycle.RUNNING
        if not run.task.goals and run.route_type != RouteType.CHAT:
            await self._compile(run)
        await self._pause(run)
        if run.is_terminal() or run.lifecycle.value.startswith("WAITING"):
            return
        if run.route_type == RouteType.CHAT:
            reply = str(run.task.binding_context.get("chat_reply", run.result_summary))
            await self._finish(run, RunLifecycle.COMPLETED, None, reply, GoalOutcome.SATISFIED)
        elif run.route_type and run.route_type.is_complex_agent():
            await self._work_multi_agent(run)
        else:
            await self._work_fast_or_legacy(run)

    async def _work_fast_or_legacy(self, run: RunRecord) -> None:
        for _ in range(16):
            if run.is_terminal() or run.lifecycle.value.startswith("WAITING"):
                return
            version, epoch, task = run.task.goal_version, self.router.epoch, run.task.model_copy(deep=True)
            if self.router.is_offline_edge:
                await self._finish(
                    run,
                    RunLifecycle.STOPPED,
                    "EDGE_UNAVAILABLE",
                    "Step Edge UNAVAILABLE：没有本地模型服务，不能继续规划",
                    GoalOutcome.UNKNOWN,
                )
                return
            snapshot = await self.executor.read(run, set(DeviceDomain))
            if await self._external_conflict(run, task, snapshot):
                await self._wait_for(run, "CLARIFICATION", "设备被外部修改，是否保留外部设置？请修改目标或停止任务")
                return
            if run.route_type == RouteType.FAST:
                plan = self.binder.action_for(task.goals[0])
                if plan is None:
                    raise ValueError("非法 FAST 目标")
                if effects_match(str(plan["capability_id"]), self.binder.params(plan), snapshot.state):
                    await self._conclude(run, version)
                    return
                plan = {**plan, "decision": "ACT", "agent_role": "MAIN", "direct_action": True}
            else:
                run.phase = RunPhase.PLAN
                run.budget.count_model()
                await self.store.append_event(
                    run,
                    "MODEL_REQUEST",
                    {"phase": "plan", "agent_role": "MAIN", "goal_version": version, "model_epoch": epoch},
                )
                prior = self._prior(run)
                hints = await _await(
                    self.memory.plan_hints(
                        run.session_id, task.raw_text, task.goals, task.constraints, snapshot, prior, run.tenant_id
                    )
                )
                await _await(self.model.request_context(run.run_id, version, run.budget.deadline, role=AgentRole.MAIN))
                plan = await _await(
                    self.model.plan_next(
                        run.run_id,
                        task.goals,
                        task.constraints,
                        [{"template_id": c.template_id, "params": c.params} for c in task.criteria],
                        snapshot,
                        prior,
                        hints,
                    )
                )
            if self._stale(run, version, epoch):
                await self.store.append_event(
                    run,
                    "PLAN_DISCARDED",
                    {"planned_version": version, "current_version": run.task.goal_version, "model_epoch": epoch},
                )
                continue
            await self.store.append_event(run, "PLAN", plan)
            decision = str(plan.get("decision"))
            if decision == "CLARIFY":
                await self._wait_for(run, "CLARIFICATION", str(plan.get("question", "请补充目标")))
                return
            if decision == "FINISH":
                await self._conclude(run, version)
                return
            if decision != "ACT":
                raise ValueError("非法模型决策")
            cap, params = str(plan.get("capability_id")), self.binder.params(plan)
            if cap in ("device.get_state", "device.read_state"):
                await _await(
                    self.model.feedback(
                        run.run_id, version, plan, {"state": snapshot.state, "revision": snapshot.revision}
                    )
                )
                continue
            if self._stale(run, version, epoch):
                continue
            run.phase = RunPhase.PREFLIGHT
            action_gate = self.preflight.check_action(run, cap, params, snapshot, version)
            await self.store.append_event(run, "ACTION_PREFLIGHT", action_gate.to_map())
            if action_gate.decision == PreflightDecision.STALE:
                continue
            if action_gate.decision == PreflightDecision.DENY:
                await self._finish(
                    run,
                    RunLifecycle.STOPPED,
                    action_gate.code or "PREFLIGHT_DENIED",
                    action_gate.message or "动作预检拒绝",
                    GoalOutcome.UNSATISFIED,
                )
                return
            if action_gate.skip_write:
                await self._conclude(run, version)
                return
            run.phase = RunPhase.ACT
            action = await self.executor.execute_write(run, cap, params, version, snapshot)
            await _await(
                self.model.feedback(
                    run.run_id,
                    version,
                    plan,
                    {
                        "execution_status": action.execution_status.value,
                        "verification_status": action.verification_status.value if action.verification_status else None,
                        "attribution": action.attribution.value,
                        "action_id": action.action_id,
                        "state": action.evidence.get("after_state"),
                    },
                )
            )
            if run.is_terminal() or run.pending:
                return
            if version != run.task.goal_version:
                continue
            if action.execution_status == ExecutionStatus.UNKNOWN:
                await self._finish(
                    run,
                    RunLifecycle.STOPPED,
                    "UNRESOLVED_ACTION",
                    "动作结果未知，已查询原动作；停止新写",
                    GoalOutcome.UNKNOWN,
                )
                return
            if action.execution_status == ExecutionStatus.REJECTED:
                await self._finish(run, RunLifecycle.STOPPED, "POLICY_DENIED", action.message, GoalOutcome.UNSATISFIED)
                return
            if action.execution_status == ExecutionStatus.APPLIED:
                run.budget.reset_same_failure()
            if action.execution_status == ExecutionStatus.NOT_APPLIED:
                run.budget.count_same_failure()
            failures = sum(
                a.capability_id == cap and a.params == params and a.execution_status == ExecutionStatus.NOT_APPLIED
                for a in run.actions
            )
            if failures >= 2 or run.route_type == RouteType.FAST:
                await self._conclude(run, version)
                return
        await self._finish(run, RunLifecycle.STOPPED, "BUDGET_EXHAUSTED_STEP", "已达到步骤上限", GoalOutcome.UNKNOWN)

    async def _work_multi_agent(self, run: RunRecord) -> None:
        version, epoch, task = run.task.goal_version, self.router.epoch, run.task.model_copy(deep=True)
        if self.router.is_offline_edge:
            await self._finish(
                run,
                RunLifecycle.STOPPED,
                "EDGE_UNAVAILABLE",
                "Step Edge UNAVAILABLE：没有本地模型服务，不能继续规划",
                GoalOutcome.UNKNOWN,
            )
            return
        snapshot = await self.executor.read(run, set(DeviceDomain))
        if await self._external_conflict(run, task, snapshot):
            await self._wait_for(run, "CLARIFICATION", "设备被外部修改，是否保留外部设置？请修改目标或停止任务")
            return
        spec = task_spec_from(task, run.run_id, self.router.active_model_id)
        await self.store.append_event(
            run, "TASK_SPEC", {"agent_role": "MAIN", "task_spec": spec.to_map(), "goal_version": version}
        )
        suggestions: list[str] = []
        draft = None
        max_rounds = max(1, run.budget.max_replans + 1)
        for round_ in range(max_rounds):
            if self._stale(run, version, epoch):
                await self.store.append_event(
                    run, "PLAN_DISCARDED", {"reason": "stale_before_planner", "goal_version": version, "round": round_}
                )
                return
            snapshot = await self.executor.read(run, set(DeviceDomain))
            run.phase = RunPhase.PLAN
            run.budget.count_model()
            await self.store.append_event(
                run,
                "MODEL_REQUEST",
                {"phase": "plan_draft", "agent_role": "PLANNER", "goal_version": version, "revision_round": round_},
            )
            await _await(self.model.request_context(run.run_id, version, run.budget.deadline, role=AgentRole.PLANNER))
            draft = await _await(
                self.model.plan_draft(run.run_id, spec, snapshot, self._prior(run), suggestions, round_)
            )
            if self._stale(run, version, epoch):
                await self.store.append_event(
                    run,
                    "PLAN_DRAFT_DISCARDED",
                    {"planned_version": version, "current_version": run.task.goal_version, "agent_role": "PLANNER"},
                )
                return
            await self.store.append_event(run, "PLAN_DRAFT", draft.to_map())
            run.phase = RunPhase.PREFLIGHT
            plan_gate = self.preflight.check_plan(run, spec, draft)
            await self.store.append_event(run, "PLAN_PREFLIGHT", plan_gate.to_map())
            if plan_gate.decision == PreflightDecision.STALE:
                return
            if plan_gate.decision == PreflightDecision.DENY:
                if plan_gate.missing_goals and round_ + 1 < max_rounds:
                    suggestions = plan_gate.missing_goals
                    await self.store.append_event(
                        run, "PLAN_PREFLIGHT_REVISE", {"missing_goals": plan_gate.missing_goals}
                    )
                    try:
                        run.budget.count_replan()
                    except RuntimeError:
                        await self._finish(
                            run,
                            RunLifecycle.STOPPED,
                            "PREFLIGHT_DENIED",
                            plan_gate.message or "计划预检未通过且无法再规划",
                            GoalOutcome.UNSATISFIED,
                        )
                        return
                    continue
                await self._finish(
                    run,
                    RunLifecycle.STOPPED,
                    plan_gate.code or "PREFLIGHT_DENIED",
                    plan_gate.message or "计划预检未通过",
                    GoalOutcome.UNSATISFIED,
                )
                return
            if not await self._execute_plan(run, draft, version, epoch):
                return
            if run.is_terminal() or run.pending:
                return
            if not await self._audit_and_maybe_replan(run, spec, draft, version, epoch):
                return
            suggestions = list(run.evaluation_snapshot.get("replan_suggestions") or [])
            if not suggestions:
                return
        await self._conclude(run, version)

    async def _execute_plan(self, run: RunRecord, draft: Any, version: int, epoch: int) -> bool:
        for planned_action in draft.actions:
            if self._stale(run, version, epoch):
                await self.store.append_event(
                    run, "LATE_PLAN_IGNORED", {"agent_role": "PLANNER", "goal_version": version}
                )
                return False
            fresh = await self.executor.read(run, set(DeviceDomain))
            cap, params = str(planned_action.get("capability_id")), self.binder.params(planned_action)
            run.phase = RunPhase.PREFLIGHT
            action_gate = self.preflight.check_action(run, cap, params, fresh, version)
            await self.store.append_event(run, "ACTION_PREFLIGHT", action_gate.to_map())
            if action_gate.decision == PreflightDecision.STALE:
                return False
            if action_gate.decision == PreflightDecision.DENY:
                await self._finish(
                    run,
                    RunLifecycle.STOPPED,
                    action_gate.code or "PREFLIGHT_DENIED",
                    action_gate.message or "动作预检拒绝",
                    GoalOutcome.UNSATISFIED,
                )
                return False
            if action_gate.skip_write or cap in ("device.get_state", "device.read_state"):
                continue
            run.phase = RunPhase.ACT
            action = await self.executor.execute_write(run, cap, params, version, fresh)
            if run.is_terminal() or run.pending:
                return False
            if version != run.task.goal_version:
                await self.store.append_event(
                    run, "LATE_RESULT_IGNORED", {"action_id": action.action_id, "planned_version": version}
                )
                return False
            if action.execution_status == ExecutionStatus.UNKNOWN:
                await self._finish(
                    run,
                    RunLifecycle.STOPPED,
                    "UNRESOLVED_ACTION",
                    "动作结果未知，已查询原动作；停止新写",
                    GoalOutcome.UNKNOWN,
                )
                return False
            if action.execution_status == ExecutionStatus.REJECTED:
                await self._finish(run, RunLifecycle.STOPPED, "POLICY_DENIED", action.message, GoalOutcome.UNSATISFIED)
                return False
        return True

    async def _audit_and_maybe_replan(self, run: RunRecord, spec: Any, draft: Any, version: int, epoch: int) -> bool:
        if self._stale(run, version, epoch):
            await self.store.append_event(run, "AUDIT_DISCARDED", {"planned_version": version, "agent_role": "REVIEWER"})
            return False
        run.phase = RunPhase.AUDIT
        goal_results, snapshot = await self.verifier.verify_goals(run)
        overall = OutcomeAggregator.aggregate(goal_results)
        await self.store.append_event(
            run,
            "GOAL_RESULTS",
            {"goal_results": [item.to_map() for item in goal_results], "agent_role": "VERIFIER"},
        )
        await self.store.append_event(
            run, "OVERALL_OUTCOME", {"overall_outcome": overall.value, "agent": "OUTCOME_AGGREGATOR"}
        )
        run.budget.count_model()
        await self.store.append_event(
            run, "MODEL_REQUEST", {"phase": "audit", "agent_role": "REVIEWER", "goal_version": version}
        )
        await _await(self.model.request_context(run.run_id, version, run.budget.deadline, role=AgentRole.REVIEWER))
        raw_audit = await _await(
            self.model.audit_execution(
                run.run_id,
                spec,
                draft,
                execution_evidence(run),
                snapshot,
                goal_results,
                overall,
            )
        )
        audit = stamp_audit(
            raw_audit,
            goal_results,
            overall,
            run_id=run.run_id,
            goal_version=version,
            model_id=self.router.active_model_id,
        )
        if self._stale(run, version, epoch):
            await self.store.append_event(run, "AUDIT_DISCARDED", {"planned_version": version, "agent_role": "REVIEWER"})
            return False
        await self.store.append_event(run, "AUDIT_RESULT", audit.to_map())
        run.evaluation_snapshot.update(
            goal_results=[item.to_map() for item in goal_results],
            overall_outcome=overall.value,
            audit={
                "explanation": audit.explanation,
                "replan_required": audit.replan_required,
                "evidence_gaps": audit.evidence_gaps,
            },
        )
        if should_replan(run, audit):
            suggestions = audit.evidence_gaps or ([audit.replan_reason] if audit.replan_reason else ["replan remaining"])
            run.evaluation_snapshot["replan_suggestions"] = suggestions
            await self.store.append_event(run, "AUDIT_REPLAN", {"suggestions": suggestions})
            return True
        await self._conclude(
            run,
            version,
            goal_results=goal_results,
            overall=overall,
            summary=audit.final_reply_draft or audit.explanation,
        )
        return False

    async def _compile(self, run: RunRecord) -> None:
        version, epoch, text = run.task.goal_version, self.router.epoch, run.task.raw_text or ""
        run.budget.count_model()
        await self.store.append_event(
            run, "MODEL_REQUEST", {"phase": "compile", "agent_role": "MAIN", "goal_version": version}
        )
        snapshot = await self.executor.read(run, set(DeviceDomain))
        hints = await _await(self.memory.compile_hints(run.session_id, text, snapshot, run.tenant_id))
        await _await(self.model.request_context(run.run_id, version, run.budget.deadline, role=AgentRole.MAIN))
        candidate: CompiledTaskCandidate = await _await(self.model.compile_task(text, snapshot, hints))
        if self._stale(run, version, epoch):
            await self.store.append_event(run, "COMPILE_DISCARDED", {"planned_version": version})
            return
        await self.store.append_event(
            run, "COMPILE", {"summary": candidate.summary, "raw": candidate.raw, "agent_role": "MAIN"}
        )
        route = ExecutionRouter().route(candidate)
        run.route_type = route
        await self.store.append_event(
            run,
            "ROUTE",
            {
                "route": route.value,
                "decision": {
                    "route": route.value,
                    "agent_role": "MAIN",
                    "direct_action": candidate.fast_action,
                    "summary": candidate.summary or "",
                },
            },
        )
        if route == RouteType.CHAT:
            run.task.binding_context["chat_reply"] = candidate.summary
            run.result_summary = candidate.summary
            return
        if route == RouteType.REJECT:
            await self._finish(
                run, RunLifecycle.STOPPED, "UNSUPPORTED", candidate.reject_reason, GoalOutcome.UNSATISFIED
            )
            return
        if route == RouteType.CLARIFY:
            await self._wait_for(run, "CLARIFICATION", candidate.clarify_question or "请补充目标")
            return
        original = run.task.binding_context.get("original_request", text)
        task = self.binder.bind(run.run_id, text, self.settings.defaults_rule_id, candidate)
        task.goal_version = version
        task.binding_context.update(
            original_request=original, baseline=snapshot.state, baseline_revision=snapshot.revision
        )
        if candidate.summary is not None:
            task.binding_context["summary"] = candidate.summary
        if candidate.fast_action is not None:
            task.binding_context["direct_action"] = candidate.fast_action
        for criterion in task.criteria:
            criterion.bound_goal_version, criterion.baseline_observation = version, snapshot.state
        run.task = task
        await self.store.append_event(
            run, "GOAL_BOUND", {"goals": task.goals, "constraints": task.constraints, "goal_version": version}
        )

    async def _external_conflict(self, run: RunRecord, task: DeviceTask, snapshot: Any) -> bool:
        baseline = int(task.binding_context.get("baseline_revision", 0))
        for criterion in task.criteria:
            if criterion.template_id != "field_eq":
                continue
            field = str(criterion.params.get("field"))
            origin = snapshot.origins.get(field)
            if origin and origin.get("origin") == "EXTERNAL" and int(origin.get("revision", 0)) > baseline:
                if not self.verifier.check(criterion, snapshot):
                    await self.store.append_event(run, "EXTERNAL_CONFLICT", {"field": field, "origin": origin})
                    return True
        return False

    def _stale(self, run: RunRecord, version: int, epoch: int) -> bool:
        return (
            run.is_terminal() or run.cancel_accepted or version != run.task.goal_version or epoch != self.router.epoch
        )

    @staticmethod
    def _prior(run: RunRecord) -> list[dict[str, Any]]:
        return [
            {
                "capability_id": a.capability_id,
                "params": a.params,
                "execution_status": a.execution_status.value,
                "action_id": a.action_id,
                "goal_version": a.goal_version,
            }
            for a in run.actions
        ]

    async def _conclude(
        self,
        run: RunRecord,
        version: int,
        goal_results: list[Any] | None = None,
        overall: OverallOutcome | None = None,
        summary: str | None = None,
    ) -> None:
        if goal_results is None or overall is None:
            computed, snapshot = await self.verifier.verify_goals(run)
            goal_results = computed
            overall = OutcomeAggregator.aggregate(goal_results)
        else:
            snapshot = await self.device.snapshot()
        if run.is_terminal() or run.task.goal_version != version:
            return
        details = [
            {
                "criterion_id": item.criterion_id,
                "template_id": item.template_id,
                "params": item.params,
                "status": "UNKNOWN"
                if item.status.value in {"UNKNOWN", "PENDING"}
                else "SATISFIED"
                if item.status.value == "SATISFIED"
                else "NOT_SATISFIED",
                "goal_status": item.status.value,
            }
            for item in goal_results
        ]
        run.evaluation_snapshot.update(
            details=details,
            goal_results=[item.to_map() for item in goal_results],
            overall_outcome=overall.value,
            state=snapshot.state,
            revision=snapshot.revision,
        )
        await self.store.append_event(
            run,
            "EVALUATE",
            {"outcome": overall.to_goal_outcome().value, "overall_outcome": overall.value, "details": details},
        )
        text = summary or (
            "结果未知，保留已知动作事实，停止新写"
            if overall == OverallOutcome.UNKNOWN
            else "仍有目标未满足，请查看逐项证据"
            if overall in {OverallOutcome.PARTIAL, OverallOutcome.FAILED}
            else Verifier._summary(run, snapshot)
        )
        await self._finish(
            run,
            overall.to_lifecycle(),
            None if overall == OverallOutcome.COMPLETED else overall.value,
            text,
            overall.to_goal_outcome(),
        )

    async def _finish(
        self,
        run: RunRecord,
        lifecycle: RunLifecycle,
        reason: str | None,
        summary: str | None,
        outcome: GoalOutcome,
    ) -> None:
        async with self.store.run_lock(run.run_id):
            await self._finish_locked(run, lifecycle, reason, summary, outcome)

    async def _finish_locked(
        self,
        run: RunRecord,
        lifecycle: RunLifecycle,
        reason: str | None,
        summary: str | None,
        outcome: GoalOutcome,
    ) -> None:
        """Caller must hold store.run_lock(run.run_id)."""
        if run.is_terminal():
            return
        deadline_task = self._deadlines.pop(run.run_id, None)
        if deadline_task and deadline_task is not asyncio.current_task():
            deadline_task.cancel()
        run.lifecycle, run.phase, run.pending = lifecycle, RunPhase.FINISH, None
        run.stop_reason, run.result_summary, run.goal_outcome = reason, summary, outcome
        if "final_state" not in run.evaluation_snapshot:
            # Snapshot outside nested awaits that could race terminal flag: capture under lock.
            snap = await self.device.snapshot()
            run.evaluation_snapshot["final_state"] = snap.state
        await self.store.append_event(
            run, "RUN_FINISHED", {"lifecycle": lifecycle.value, "stop_reason": reason, "summary": summary}
        )
        await self.persistence.persist_run(run)
        self._on_terminal(run, lifecycle)

    def _on_terminal(self, run: RunRecord, lifecycle: RunLifecycle) -> None:
        if self.platform is None:
            return
        if lifecycle == RunLifecycle.COMPLETED:
            self.platform.metrics.inc("runs_completed")
        elif lifecycle == RunLifecycle.CANCELLED:
            self.platform.metrics.inc("runs_cancelled")
        elif lifecycle == RunLifecycle.INTERRUPTED:
            self.platform.metrics.inc("runs_interrupted")
            self.platform.dead_letters.add(run, "interrupted")
        elif lifecycle in {RunLifecycle.FAILED, RunLifecycle.STOPPED, RunLifecycle.TIMED_OUT}:
            self.platform.metrics.inc("runs_failed")
            self.platform.dead_letters.add(run, lifecycle.value)
        if run.unresolved_unknown:
            self.platform.dead_letters.add(run, "unresolved_unknown")
        self.platform.audit.emit(
            "run_finished",
            tenant_id=run.tenant_id,
            actor=run.actor,
            run_id=run.run_id,
            result=lifecycle.value,
            detail={"stop_reason": run.stop_reason},
        )

    async def _wait_for(self, run: RunRecord, type_: str, question: str) -> None:
        if run.is_terminal():
            return
        run.pending = PendingInteraction(
            type=type_, goal_version=run.task.goal_version, question=question, expires_at=run.budget.deadline or now()
        )
        run.lifecycle, run.phase, run.result_summary = RunLifecycle.WAITING_CLARIFICATION, RunPhase.WAIT, question
        await self.store.append_event(run, "WAIT_CLARIFICATION", run.pending.to_map())

    async def cancel(self, id_: str) -> RunRecord:
        run = self._get(id_)
        async with self.store.run_lock(run.run_id):
            if run.is_terminal():
                return run
            run.cancel_accepted = True
            await self._invalidate_pending(run)
            await self.store.append_event(run, "CANCEL_ACCEPTED", {"in_flight": run.in_flight_action_id})
            await self._finish_locked(
                run,
                RunLifecycle.CANCELLED,
                "USER_CANCEL",
                "已取消后续执行；取消前在途动作仍可能生效",
                GoalOutcome.UNKNOWN,
            )
        return run

    async def intervene(
        self,
        id_: str,
        type_: str | None,
        text: str | None,
        expected: int | None = None,
        resume: bool = True,
    ) -> RunRecord:
        if (type_ or "").upper() == "CANCEL" or text in ("停止任务", "取消任务"):
            return await self.cancel(id_)
        run, value = self._get(id_), text or ""
        self._ensure_mutable(run, expected)
        task, version = run.task, run.task.goal_version + 1
        if not task.goals:
            raise RuntimeError("仍在理解原目标；可取消，或等待目标出现后修改")
        applied = False
        if any(x in value for x in ("空调先不要", "不调空调", "空调不要")):
            task.goals = [
                g
                for g in task.goals
                if not ((a := self.binder.action_for(g)) and str(a["capability_id"]).startswith("climate."))
            ]
            task.constraints.append({"type": "no_cabin_write"})
            applied = True
        if "媒体不要" in value or "保持外部" in value:
            task.goals = [
                g
                for g in task.goals
                if not ((a := self.binder.action_for(g)) and str(a["capability_id"]).startswith("media."))
            ]
            task.constraints.append({"type": "no_media_write"})
            applied = True
        temperature = self.extract_intervene_temperature(value)
        if temperature is not None:
            task.goals = [
                g
                for g in task.goals
                if not ((a := self.binder.action_for(g)) and a["capability_id"] == "climate.set_temperature")
            ]
            task.goals.append({"type": "cabin_temperature", "value": temperature})
            applied = True
        if "移除保留导航" in value or "不用保留导航" in value:
            task.constraints = [c for c in task.constraints if c.get("type") != "keep_navigation_prompt"]
            applied = True
        if not applied:
            raise ValueError("修改未被应用：请明确温度、删除空调目标、保留外部媒体设置或取消")
        if not task.goals and not task.constraints:
            task.goal_version = version
            await self._finish(run, RunLifecycle.STOPPED, "GOALS_REMOVED", "全部目标已移除", GoalOutcome.UNSATISFIED)
            return run
        candidate = CompiledTaskCandidate(goals=task.goals, constraints=task.constraints, summary=value)
        updated = self.binder.bind(run.run_id, task.raw_text or "", self.settings.defaults_rule_id, candidate)
        updated.goal_version = version
        updated.binding_context.update(task.binding_context)
        for criterion in updated.criteria:
            criterion.bound_goal_version = version
        run.task = updated
        await self._invalidate_pending(run)
        run.lifecycle, run.route_type = RunLifecycle.RUNNING, RouteType.MULTI_AGENT
        await self.store.append_event(
            run,
            "GOAL_CHANGED",
            {"goal_version": version, "text": value, "goals": updated.goals, "constraints": updated.constraints},
        )
        if resume:
            await self._launch(run, False)
        return run

    @staticmethod
    def extract_intervene_temperature(text: str | None) -> int | None:
        match = re.search(r"(?:温度|空调)?\s*(?:改成|设为|调整为|调到)\s*(\d{1,2})\s*度?", text or "")
        if not match:
            return None
        value = int(match.group(1))
        if not 16 <= value <= 30:
            raise ValueError("有效温度16至30℃")
        return value

    @staticmethod
    def _ensure_mutable(run: RunRecord, version: int | None) -> None:
        if run.is_terminal() or run.budget.expired():
            raise RuntimeError("任务已结束或到期")
        if version is not None and version != run.task.goal_version:
            raise RuntimeError("goal_version 冲突")

    async def _invalidate_pending(self, run: RunRecord) -> None:
        if run.pending:
            await self.store.append_event(run, "PENDING_INVALIDATED", {"pending_id": run.pending.pending_id})
        run.pending = None
        for action in run.actions:
            if action.execution_status == ExecutionStatus.PROPOSED:
                action.execution_status = ExecutionStatus.CANCELLED_BEFORE_DISPATCH

    async def answer_clarification(self, id_: str, answer: str) -> RunRecord:
        run = self._get(id_)
        self._ensure_mutable(run, None)
        if run.lifecycle != RunLifecycle.WAITING_CLARIFICATION:
            raise RuntimeError("当前不在澄清等待")
        text, version = f"{run.task.raw_text}；用户补充：{answer}", run.task.goal_version + 1
        original = run.task.binding_context.get("original_request")
        run.task = DeviceTask(goal_version=version, raw_text=text, binding_context={"original_request": original})
        run.pending, run.lifecycle = None, RunLifecycle.RUNNING
        await self.store.append_event(run, "CLARIFICATION_ANSWER", {"answer": answer})
        await self._launch(run, True)
        return run

    async def answer_pending(
        self,
        id_: str,
        pending_id: str,
        version: int,
        decision: str,
        answer: str | None = None,
    ) -> RunRecord:
        run = self._get(id_)
        self._ensure_mutable(run, version)
        pending = run.pending
        if (
            not pending
            or pending.pending_id != pending_id
            or pending.goal_version != version
            or pending.expires_at <= now()
        ):
            raise RuntimeError("确认对象已失效")
        if decision == "REJECT":
            await self.store.append_event(run, "CONFIRM_REJECTED", {"pending_id": pending_id})
            await self._finish(run, RunLifecycle.STOPPED, "USER_DECLINED", "用户拒绝执行", GoalOutcome.UNSATISFIED)
            return run
        if decision == "ANSWER":
            return await self.answer_clarification(id_, answer or "")
        if decision != "APPROVE" or pending.type != "CONFIRMATION":
            raise ValueError("无效回答")
        run.pending, run.lifecycle = None, RunLifecycle.RUNNING
        run.task.binding_context["approved_action"] = {
            "capability_id": pending.capability_id,
            "params": pending.params,
            "goal_version": version,
        }
        await self.store.append_event(run, "CONFIRM_APPROVED", {"pending_id": pending_id})
        await self._launch(run, True)
        return run

    async def reset_experiment(self) -> dict[str, Any]:
        interrupted = []
        for run in self.store.list():
            if not run.is_terminal() and run.device_id == self.device.device_id:
                await self.cancel(run.run_id)
                interrupted.append(run.run_id)
        await self.device.force_new_environment()
        await self.device.reset_to_defaults()
        return {
            "ok": True,
            "interrupted_runs": interrupted,
            "environment_id": self.device.environment_id,
            "note": "实验重置会先取消同设备活动任务，再重建模拟环境",
        }

    def _get(self, id_: str, tenant_id: str | None = None) -> RunRecord:
        run = self.store.find(id_)
        if run is None or (tenant_id and run.tenant_id != tenant_id):
            raise ValueError("run not found")
        return run

    def list_runs(self, tenant_id: str | None = None) -> list[RunRecord]:
        return sorted(self.store.list(tenant_id), key=lambda r: r.created_at, reverse=True)

    def replay(self, id_: str) -> dict[str, Any]:
        run = self._get(id_)
        return {"mode": "history_replay", "run": self.to_view(run), "events": self.store.events_after(id_, 0)}

    def to_view(self, run: RunRecord) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "request_id": run.request_id,
            "device_id": run.device_id,
            "environment_id": run.environment_id,
            "lifecycle": run.lifecycle.value,
            "phase": run.phase.value,
            "route": run.route_type.value if run.route_type else None,
            "stop_reason": run.stop_reason,
            "result_summary": run.result_summary,
            "goal_outcome": run.goal_outcome.value if run.goal_outcome else None,
            "goal_version": run.task.goal_version,
            "raw_text": run.task.raw_text,
            "goals": deepcopy(run.task.goals),
            "constraints": deepcopy(run.task.constraints),
            "criteria": [_criterion_view(c) for c in run.task.criteria],
            "pending": run.pending.to_map() if run.pending else None,
            "budget": run.budget.to_map(),
            "actions": [_action_view(a) for a in run.actions],
            "evaluation_snapshot": deepcopy(run.evaluation_snapshot),
            "model_mode": run.evaluation_snapshot.get("model_mode"),
            "model_id": run.evaluation_snapshot.get("model_id"),
            "model_placement": self.router.placement,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "event_count": len(run.events),
            "defaults_rule_id": self.settings.defaults_rule_id,
            "tenant_id": run.tenant_id,
            "trace_id": run.trace_id,
            "actor": run.actor,
        }


def _criterion_view(criterion: Any) -> dict[str, Any]:
    data = criterion.model_dump(mode="json") if hasattr(criterion, "model_dump") else dict(criterion)
    return {
        **data,
        "criterionId": data.get("criterion_id"),
        "templateId": data.get("template_id"),
        "sourceRef": data.get("source_ref"),
        "baselineObservation": data.get("baseline_observation"),
        "boundGoalVersion": data.get("bound_goal_version"),
        "boundAt": data.get("bound_at"),
    }


def _action_view(action: Any) -> dict[str, Any]:
    data = action.model_dump(mode="json") if hasattr(action, "model_dump") else dict(action)
    return {
        **data,
        "actionId": data.get("action_id"),
        "idempotencyKey": data.get("idempotency_key"),
        "runId": data.get("run_id"),
        "goalVersion": data.get("goal_version"),
        "environmentId": data.get("environment_id"),
        "capabilityId": data.get("capability_id"),
        "expectedRevisions": data.get("expected_revisions"),
        "preparedAt": data.get("prepared_at"),
        "dispatchedAt": data.get("dispatched_at"),
        "finishedAt": data.get("finished_at"),
        "executionStatus": data.get("execution_status"),
        "verificationStatus": data.get("verification_status"),
        "retryOf": data.get("retry_of"),
    }
