"""Upgrade-path contracts: Preflight, Auditor, Verifier tool, Outcome Aggregator."""

from __future__ import annotations

import uuid

import pytest

from terminal_agent.agent.contracts import PlanDraft, TaskSpec
from terminal_agent.agent.multi_agent import MultiAgentSupport
from terminal_agent.capability.core import CapabilityRegistry
from terminal_agent.contracts import (
    AuditResult,
    GoalResult,
    GoalResultStatus,
    OverallOutcome,
    PreflightDecision,
    ReviewDecision,
    RunLifecycle,
    RunRecord,
)
from terminal_agent.device.simulator import DeviceSimulator
from terminal_agent.model.fake import FakeModelAdapter
from terminal_agent.persistence.sqlite import SqlitePersistence
from terminal_agent.persistence.store import InMemoryRunStore
from terminal_agent.policy.engine import PolicyEngine
from terminal_agent.runtime.auditor import stamp_audit
from terminal_agent.runtime.executor import CapabilityExecutor
from terminal_agent.runtime.harness import HarnessService
from terminal_agent.runtime.outcome import OutcomeAggregator
from terminal_agent.runtime.preflight import PreflightGate
from terminal_agent.runtime.support import ModelRouter, RuntimeSettings, TaskBinder
from terminal_agent.runtime.verifier import Verifier


def _stack(tmp_path):
    registry = CapabilityRegistry()
    sim = DeviceSimulator(registry)
    store = InMemoryRunStore(str(tmp_path / "events"))
    policy = PolicyEngine(registry)
    executor = CapabilityExecutor(sim, registry, policy, store, fresh_window_ms=2000)
    harness = HarnessService(
        store,
        sim,
        FakeModelAdapter(),
        TaskBinder(registry),
        executor,
        Verifier(sim),
        SqlitePersistence(store, sim, str(tmp_path / "db.sqlite"), enabled=False),
        RuntimeSettings(),
        router=ModelRouter(),
    )
    sim.start_clock()
    return harness, sim, store, PreflightGate(registry, policy)


def test_outcome_aggregator_rules() -> None:
    def item(status: GoalResultStatus, required: bool = True) -> GoalResult:
        return GoalResult(criterion_id=status.value, template_id="t", status=status, required=required)

    assert OutcomeAggregator.aggregate([]) == OverallOutcome.COMPLETED
    assert OutcomeAggregator.aggregate([item(GoalResultStatus.SATISFIED)]) == OverallOutcome.COMPLETED
    assert OutcomeAggregator.aggregate([item(GoalResultStatus.UNSATISFIED)]) == OverallOutcome.FAILED
    assert (
        OutcomeAggregator.aggregate([item(GoalResultStatus.SATISFIED), item(GoalResultStatus.UNSATISFIED)])
        == OverallOutcome.PARTIAL
    )
    assert OutcomeAggregator.aggregate([item(GoalResultStatus.UNKNOWN)]) == OverallOutcome.UNKNOWN
    assert OutcomeAggregator.aggregate([item(GoalResultStatus.PENDING)]) == OverallOutcome.UNKNOWN
    assert OutcomeAggregator.aggregate([item(GoalResultStatus.SCHEDULED)]) == OverallOutcome.PARTIAL
    assert OutcomeAggregator.aggregate([item(GoalResultStatus.UNSATISFIED, required=False)]) == OverallOutcome.COMPLETED


def test_auditor_cannot_override_deterministic_results() -> None:
    facts = [GoalResult(criterion_id="c1", template_id="field_eq", status=GoalResultStatus.UNSATISFIED)]
    forged = AuditResult(
        explanation="其实已经完成",
        replan_required=False,
        goal_results=[GoalResult(criterion_id="c1", template_id="field_eq", status=GoalResultStatus.SATISFIED)],
        overall_outcome=OverallOutcome.COMPLETED,
    )
    stamped = stamp_audit(forged, facts, OverallOutcome.FAILED, run_id="run_1", goal_version=1)
    assert stamped.overall_outcome == OverallOutcome.FAILED
    assert stamped.goal_results[0].status == GoalResultStatus.UNSATISFIED
    assert stamped.replan_required is True or stamped.explanation == "其实已经完成"
    completed = stamp_audit(
        AuditResult(replan_required=True, replan_reason="ignore me"),
        [GoalResult(criterion_id="c1", template_id="t", status=GoalResultStatus.SATISFIED)],
        OverallOutcome.COMPLETED,
    )
    assert completed.replan_required is False
    assert completed.overall_outcome == OverallOutcome.COMPLETED


def test_plan_preflight_denies_window_against_no_window() -> None:
    spec = TaskSpec(
        goals=[{"type": "window_position", "window": "front_left", "position": 50}],
        constraints=[{"type": "no_window"}],
        allowed_capabilities=["window.set_position"],
        goal_version=1,
    )
    draft = PlanDraft(
        actions=[{"capability_id": "window.set_position", "params": {"window": "front_left", "position": 50}}]
    )
    review = MultiAgentSupport.review(spec, draft, "fake")
    assert review.decision == ReviewDecision.REJECT
    run = RunRecord(run_id="r", request_id="q", device_id="d", environment_id="e")
    run.task.goal_version = 1
    gate = PreflightGate(CapabilityRegistry(), PolicyEngine(CapabilityRegistry()))
    result = gate.check_plan(run, spec, draft)
    assert result.decision == PreflightDecision.DENY
    assert result.violated_constraints


@pytest.mark.asyncio
async def test_fast_skips_planner_and_auditor(tmp_path) -> None:
    harness, sim, store, _ = _stack(tmp_path)
    run = await harness.create_run(f"fast-{uuid.uuid4()}", "把空调设为 23 度", "test", True)
    types = {e.type for e in store.events_after(run.run_id, 0)}
    assert run.route_type and run.route_type.value == "FAST"
    assert run.lifecycle == RunLifecycle.COMPLETED
    assert "PLAN_DRAFT" not in types
    assert "AUDIT_RESULT" not in types
    assert "ACTION_PREFLIGHT" in types
    sim.stop_clock()


@pytest.mark.asyncio
async def test_multi_agent_uses_auditor_not_reviewer(tmp_path) -> None:
    harness, sim, store, _ = _stack(tmp_path)
    run = await harness.create_run(
        f"multi-{uuid.uuid4()}",
        "后排要休息，把座舱调整舒服一点；媒体声音调低，但保留导航提示，不要开窗。",
        "test",
        True,
    )
    types = {e.type for e in store.events_after(run.run_id, 0)}
    assert run.route_type and run.route_type.value == "MULTI_AGENT"
    assert run.lifecycle.value in {"COMPLETED", "PARTIAL"}
    assert "PLAN_PREFLIGHT" in types
    assert "AUDIT_RESULT" in types
    assert "REVIEW_RESULT" not in types
    assert run.evaluation_snapshot.get("overall_outcome")
    assert all(not str(a.capability_id).startswith("window.") for a in run.actions)
    sim.stop_clock()
