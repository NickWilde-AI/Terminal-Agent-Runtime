"""Eval runner — behavioral port of Java EvalRunner."""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from terminal_agent.capability.core import CapabilityRegistry
from terminal_agent.contracts import ExecutionStatus, RunLifecycle, RunRecord, now
from terminal_agent.device.port import FaultType
from terminal_agent.device.simulator import DeviceSimulator
from terminal_agent.eval.cases import EvalCase, EvalCatalog
from terminal_agent.model.fake import FakeModelAdapter
from terminal_agent.persistence.sqlite import SqlitePersistence
from terminal_agent.persistence.store import InMemoryRunStore
from terminal_agent.policy.engine import PolicyEngine
from terminal_agent.runtime.baseline import BaselineRunner
from terminal_agent.runtime.executor import CapabilityExecutor
from terminal_agent.runtime.harness import HarnessService
from terminal_agent.runtime.support import ModelRouter, RuntimeSettings, TaskBinder
from terminal_agent.runtime.verifier import Verifier


def _eq(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return int(a) == int(b)
    return str(a) == str(b)


def _has_event(run: RunRecord, type_: str) -> bool:
    return any(e.type == type_ for e in run.events)


class EvalRunner:
    def __init__(
        self,
        harness: HarnessService,
        simulator: DeviceSimulator,
        store: InMemoryRunStore,
        policy: PolicyEngine,
        registry: CapabilityRegistry,
        model: Any,
        baseline: BaselineRunner,
        settings: Any | None = None,
        report_dir: str | Path = "reports",
    ) -> None:
        self.harness = harness
        self.simulator = simulator
        self.store = store
        self.policy = policy
        self.registry = registry
        self.model = model
        self.baseline = baseline
        self.settings = settings
        self.report_dir = Path(report_dir)
        self.last_report: dict[str, Any] | None = None

    @classmethod
    def create_standalone(cls, report_dir: str | Path | None = None) -> EvalRunner:
        """Wire a disposable fake-mode stack for tests / CLI."""
        tmp = tempfile.mkdtemp(prefix="eval-")
        registry = CapabilityRegistry()
        simulator = DeviceSimulator(registry)
        store = InMemoryRunStore(tmp)
        policy = PolicyEngine(registry, False)
        executor = CapabilityExecutor(simulator, registry, policy, store)
        verifier = Verifier(simulator)
        persistence = SqlitePersistence(store, simulator, f"{tmp}/db.sqlite", enabled=False)
        model = FakeModelAdapter()
        settings = RuntimeSettings()
        binder = TaskBinder(registry)
        harness = HarnessService(
            store, simulator, model, binder, executor, verifier, persistence, settings, router=ModelRouter()
        )
        baseline = BaselineRunner(store, simulator, model, binder, executor, verifier, persistence, settings)
        simulator.start_clock()

        class _Props:
            require_confirmation = False

        return cls(
            harness,
            simulator,
            store,
            policy,
            registry,
            model,
            baseline,
            settings=_Props(),
            report_dir=report_dir or Path(tmp) / "reports",
        )

    def lastReport(self) -> dict[str, Any] | None:  # noqa: N802 — Java parity alias
        return self.last_report

    async def run(self, mode: str = "agent") -> dict[str, Any]:
        cases = EvalCatalog.all()
        results: list[dict[str, Any]] = []
        passed = 0
        false_success = 0
        for case in cases:
            one = await self._run_one(case, mode)
            results.append(one)
            if one.get("passed") is True:
                passed += 1
            if one.get("false_success") is True:
                false_success += 1
        report: dict[str, Any] = {
            "mode": mode,
            "dataset_version": "eval-seeds-v1",
            "model_mode": self.model.mode(),
            "total": len(cases),
            "passed": passed,
            "failed": len(cases) - passed,
            "correct_handling_rate": 0.0 if not cases else passed / len(cases),
            "false_success": false_success,
            "cases": results,
            "generated_at": now().isoformat(),
            "note": "agent=状态反馈循环；baseline=单次计划后执行且不回传工具结果。Fake 与真实 API 报告分开，不可混算",
        }
        self.last_report = report
        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            file = self.report_dir / f"eval-{mode}-{int(time.time() * 1000)}.json"
            text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
            file.write_text(text, encoding="utf-8")
            report["report_path"] = str(file)
            (self.report_dir / f"last-{mode}.json").write_text(text, encoding="utf-8")
        except OSError:
            pass
        return report

    async def _run_one(self, c: EvalCase, mode: str) -> dict[str, Any]:
        out: dict[str, Any] = {"id": c.id, "category": c.category, "completable": c.completable}
        try:
            self.harness.release_eval_pause()
            for r in self.store.list():
                r.unresolved_unknown = False
                if not r.is_terminal():
                    r.cancel_accepted = True
                    r.lifecycle = RunLifecycle.CANCELLED
            await self.harness.await_idle(3_000)
            await self.simulator.force_new_environment()
            try:
                await self.simulator.reset_to_defaults()
            except RuntimeError:
                await self.simulator.force_new_environment()
                await self.simulator.reset_to_defaults()
            if c.initial_state:
                await self.simulator.apply_initial_state(c.initial_state)
            if c.fault_type:
                await self.simulator.inject_fault(
                    FaultType(c.fault_type), c.fault_capability, c.fault_times
                )

            if c.category == "policy" and c.candidate_capability is not None:
                return self._run_policy_case(c, out)

            old_confirm = bool(getattr(self.settings, "require_confirmation", False)) if self.settings else False
            if c.require_confirmation and self.settings is not None:
                self.settings.require_confirmation = True
                self.policy.require_confirmation = True

            needs_mid = mode != "baseline" and (
                c.intervene_text is not None or c.external_after_compile is not None or c.cancel
            )
            try:
                if mode == "baseline":
                    run = await self.baseline.run(f"eval-{c.id}-{uuid.uuid4()}", c.request or "")
                else:
                    if needs_mid:
                        self.harness.arm_eval_pause_after_goal_bound()
                    run = await self.harness.create_run(
                        f"eval-{c.id}-{uuid.uuid4()}",
                        c.request or "",
                        "eval",
                        not needs_mid,
                    )

                if needs_mid:
                    await self._wait_until(
                        run,
                        lambda r: r.is_terminal()
                        or r.lifecycle
                        in (RunLifecycle.WAITING_CLARIFICATION, RunLifecycle.WAITING_CONFIRMATION)
                        or _has_event(r, "GOAL_BOUND")
                        or _has_event(r, "EVAL_PAUSE"),
                        8_000,
                    )
                    run = self.store.find(run.run_id) or run

                if c.clarify_answer is not None and run.lifecycle == RunLifecycle.WAITING_CLARIFICATION:
                    if needs_mid:
                        self.harness.release_eval_pause()
                    run = await self.harness.answer_clarification(run.run_id, c.clarify_answer)
                    if needs_mid and (
                        c.intervene_text is not None or c.external_after_compile is not None or c.cancel
                    ):
                        self.harness.arm_eval_pause_after_goal_bound()
                        await self._wait_until(
                            run,
                            lambda r: r.is_terminal()
                            or r.lifecycle == RunLifecycle.WAITING_CONFIRMATION
                            or _has_event(r, "GOAL_BOUND")
                            or _has_event(r, "EVAL_PAUSE"),
                            8_000,
                        )
                        run = self.store.find(run.run_id) or run

                if c.external_after_compile is not None and not run.is_terminal():
                    for field, value in c.external_after_compile.items():
                        await self.simulator.external_change(field, value)

                if c.intervene_text is not None and not run.is_terminal():
                    run = await self.harness.intervene(
                        run.run_id,
                        "CHANGE_GOAL",
                        c.intervene_text,
                        run.task.goal_version,
                        False,
                    )

                if needs_mid:
                    self.harness.release_eval_pause()

                if c.require_confirmation and c.confirm_decision is not None:
                    await self._wait_until(
                        run,
                        lambda r: r.is_terminal()
                        or (r.lifecycle == RunLifecycle.WAITING_CONFIRMATION and r.pending is not None),
                        8_000,
                    )
                    run = self.store.find(run.run_id) or run
                    if run.lifecycle == RunLifecycle.WAITING_CONFIRMATION and run.pending is not None:
                        run = await self.harness.answer_pending(
                            run.run_id,
                            run.pending.pending_id,
                            run.pending.goal_version,
                            c.confirm_decision,
                            None,
                        )

                if c.force_clarify_timeout and run.lifecycle == RunLifecycle.WAITING_CLARIFICATION:
                    run.budget.deadline = now() - timedelta(seconds=1)
                    await self._wait_until(run, RunRecord.is_terminal, 3_000)
                    run = self.store.find(run.run_id) or run

                if c.cancel and not run.is_terminal():
                    run = await self.harness.cancel(run.run_id)

                if needs_mid:
                    await self._wait_until(run, RunRecord.is_terminal, 12_000)
                    run = self.store.find(run.run_id) or run

                await self.simulator.clear_fault()

                out["lifecycle"] = run.lifecycle.value if run.lifecycle else None
                out["route"] = run.route_type.value if run.route_type else None
                out["goal_outcome"] = run.goal_outcome.value if run.goal_outcome else None
                out["stop_reason"] = run.stop_reason

                errors: list[str] = []
                if c.allowed_lifecycles is not None and (run.lifecycle is None or run.lifecycle.value not in c.allowed_lifecycles):
                    errors.append(f"lifecycle={run.lifecycle}")
                if c.expected_route is not None and (
                    run.route_type is None or c.expected_route != run.route_type.value
                ):
                    errors.append(f"route={run.route_type}")

                state = (await self.simulator.read_state(None)).state
                if c.final_state_equals:
                    for key, expected in c.final_state_equals.items():
                        if not _eq(state.get(key), expected):
                            errors.append(f"state.{key}={state.get(key)} expected {expected}")

                if c.forbid_capabilities:
                    skip_statuses = {"BLOCKED", "SKIPPED", "PREPARED"}
                    for cap in c.forbid_capabilities:
                        wrote = False
                        for a in run.actions:
                            status_name = a.execution_status.value if hasattr(a.execution_status, "value") else str(a.execution_status)
                            if a.capability_id == cap and status_name not in skip_statuses:
                                wrote = True
                                break
                        if wrote:
                            errors.append(f"forbidden capability dispatched: {cap}")

                if c.require_no_writes and any(a.execution_status == ExecutionStatus.APPLIED for a in run.actions):
                    errors.append("expected no APPLIED writes")

                if c.require_applied_capability:
                    want = self.registry.canonical(c.require_applied_capability)
                    ok = any(
                        self.registry.canonical(a.capability_id) == want
                        and a.execution_status == ExecutionStatus.APPLIED
                        for a in run.actions
                    )
                    if not ok:
                        errors.append(f"missing APPLIED {c.require_applied_capability}")

                if run.lifecycle == RunLifecycle.COMPLETED and c.final_state_equals:
                    for key, expected in c.final_state_equals.items():
                        if not _eq(state.get(key), expected):
                            out["false_success"] = True
                            errors.append(f"false success on {key}")

                pass_ = not errors
                out["passed"] = pass_
                out["message"] = "ok" if pass_ else "; ".join(errors)
                out["details"] = {"state": state, "actions": len(run.actions), "exec_mode": mode}
                return out
            finally:
                self.harness.release_eval_pause()
                if c.require_confirmation and self.settings is not None:
                    self.settings.require_confirmation = old_confirm
                    self.policy.require_confirmation = old_confirm
        except Exception as ex:  # noqa: BLE001 — mirror Java catch-all per case
            out["passed"] = False
            out["message"] = str(ex)
            return out

    def _run_policy_case(self, c: EvalCase, out: dict[str, Any]) -> dict[str, Any]:
        stub = RunRecord(
            run_id="policy",
            request_id="policy",
            device_id=self.simulator.device_id,
            environment_id=self.simulator.environment_id,
        )
        stub.task.constraints = list(c.constraints or [])
        decision = self.policy.decide(stub, c.candidate_capability or "", dict(c.candidate_params or {}))
        denied = decision.decision.value == "DENY" or self.registry.get(c.candidate_capability or "") is None
        if c.candidate_capability is not None and not self.registry.validate(
            c.candidate_capability, dict(c.candidate_params or {})
        ).ok:
            denied = True
        pass_ = c.expect_deny == denied
        out["passed"] = pass_
        out["lifecycle"] = "N/A"
        out["message"] = "ok" if pass_ else f"policy decision={decision.decision}"
        return out

    async def _wait_until(
        self, run: RunRecord, pred: Callable[[RunRecord], bool], timeout_ms: int
    ) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            latest = self.store.find(run.run_id) or run
            if pred(latest):
                return
            await asyncio.sleep(0.02)
