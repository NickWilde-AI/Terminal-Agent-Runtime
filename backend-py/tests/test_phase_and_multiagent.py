"""Port of Java Phase1 / Phase2-3 / MultiAgent path tests."""

from __future__ import annotations

import uuid

import pytest

from terminal_agent.agent.contracts import PlanDraft, TaskSpec
from terminal_agent.agent.multi_agent import MultiAgentSupport
from terminal_agent.capability.core import CapabilityRegistry
from terminal_agent.contracts import ExecutionStatus, ReviewDecision, RunLifecycle
from terminal_agent.device.port import FaultType
from terminal_agent.device.simulator import DeviceSimulator
from terminal_agent.eval.runner import EvalRunner
from terminal_agent.model.fake import FakeModelAdapter
from terminal_agent.persistence.sqlite import SqlitePersistence
from terminal_agent.persistence.store import InMemoryRunStore
from terminal_agent.policy.engine import PolicyEngine
from terminal_agent.runtime.baseline import BaselineRunner
from terminal_agent.runtime.executor import CapabilityExecutor
from terminal_agent.runtime.harness import HarnessService
from terminal_agent.runtime.support import ModelRouter, RuntimeSettings, TaskBinder
from terminal_agent.runtime.verifier import Verifier


def _stack(tmp_path, require_confirmation: bool = False):
    registry = CapabilityRegistry()
    sim = DeviceSimulator(registry)
    store = InMemoryRunStore(str(tmp_path / "events"))
    policy = PolicyEngine(registry, require_confirmation)
    executor = CapabilityExecutor(sim, registry, policy, store, fresh_window_ms=2000)
    verifier = Verifier(sim)
    persistence = SqlitePersistence(store, sim, str(tmp_path / "db.sqlite"), enabled=False)
    settings = RuntimeSettings()

    class Props:
        pass

    props = Props()
    props.require_confirmation = require_confirmation
    harness = HarnessService(
        store,
        sim,
        FakeModelAdapter(),
        TaskBinder(registry),
        executor,
        verifier,
        persistence,
        settings,
        router=ModelRouter(),
    )
    baseline = BaselineRunner(store, sim, FakeModelAdapter(), TaskBinder(registry), executor, verifier, persistence, settings)
    eval_runner = EvalRunner(harness, sim, store, policy, registry, FakeModelAdapter(), baseline, settings=props)
    sim.start_clock()
    return harness, sim, store, policy, props, eval_runner


async def _reset(harness: HarnessService, sim: DeviceSimulator, store: InMemoryRunStore) -> None:
    harness.release_eval_pause()
    for run in store.list():
        run.unresolved_unknown = False
        if not run.is_terminal():
            run.lifecycle = RunLifecycle.CANCELLED
    await harness.await_idle(2000)
    await sim.force_new_environment()
    await sim.reset_to_defaults()


@pytest.mark.asyncio
async def test_phase1_temperature_and_already_satisfied(tmp_path) -> None:
    harness, sim, store, *_rest = _stack(tmp_path)
    await _reset(harness, sim, store)
    await sim.external_change("temperature_setpoint", 26)
    run = await harness.create_run(f"req-{uuid.uuid4()}", "把空调设为 23 度", "test", True)
    assert run.route_type and run.route_type.value == "FAST"
    assert run.lifecycle == RunLifecycle.COMPLETED
    assert (await sim.read_state(None)).state["temperature_setpoint"] == 23
    assert any(a.execution_status == ExecutionStatus.APPLIED for a in run.actions)

    await _reset(harness, sim, store)
    await sim.external_change("temperature_setpoint", 23)
    run2 = await harness.create_run(f"req-{uuid.uuid4()}", "把空调设为 23 度", "test", True)
    assert run2.lifecycle == RunLifecycle.COMPLETED
    assert all(a.execution_status != ExecutionStatus.APPLIED for a in run2.actions)
    sim.stop_clock()


@pytest.mark.asyncio
async def test_phase1_ack_not_applied_and_window_and_rest(tmp_path) -> None:
    harness, sim, store, *_ = _stack(tmp_path)
    await _reset(harness, sim, store)
    await sim.external_change("temperature_setpoint", 26)
    await sim.inject_fault(FaultType.ACK_NOT_APPLIED, "cabin.set_temperature", 1)
    run = await harness.create_run(f"req-{uuid.uuid4()}", "把空调设为 23 度", "test", True)
    assert (await sim.read_state(None)).state["temperature_setpoint"] == 26
    assert any(a.execution_status == ExecutionStatus.NOT_APPLIED for a in run.actions)
    assert not (
        run.lifecycle == RunLifecycle.COMPLETED and run.goal_outcome and run.goal_outcome.value == "SATISFIED"
    )

    await _reset(harness, sim, store)
    run2 = await harness.create_run(f"req-{uuid.uuid4()}", "打开左前车窗一半", "test", True)
    assert run2.lifecycle == RunLifecycle.COMPLETED
    state = (await sim.read_state(None)).state
    assert state["window_front_left"] == 50
    assert state["window_front_right"] == 0

    await _reset(harness, sim, store)
    rest = await harness.create_run(
        f"req-{uuid.uuid4()}",
        "后排要休息，把座舱调整舒服一点；媒体声音调低，但保留导航提示，不要开窗。",
        "test",
        True,
    )
    assert rest.route_type and rest.route_type.value == "MULTI_AGENT"
    assert rest.lifecycle.value in {"COMPLETED", "PARTIAL"}
    state = (await sim.read_state(None)).state
    assert state["temperature_setpoint"] == 23
    assert state["fan_level"] == 1
    assert state["media_volume"] == 6
    assert state["window_open"] is False
    sim.stop_clock()


@pytest.mark.asyncio
async def test_phase2_response_lost_delay_nav_confirm_reset(tmp_path) -> None:
    harness, sim, store, policy, props, _ = _stack(tmp_path)
    await _reset(harness, sim, store)
    await sim.external_change("temperature_setpoint", 26)
    await sim.inject_fault(FaultType.APPLIED_RESPONSE_LOST, "cabin.set_temperature", 1)
    run = await harness.create_run(f"f03-{uuid.uuid4()}", "把空调设为 23 度", "test", True)
    assert (await sim.read_state(None)).state["temperature_setpoint"] == 23
    assert any(a.execution_status == ExecutionStatus.APPLIED for a in run.actions)
    assert run.lifecycle == RunLifecycle.COMPLETED

    await _reset(harness, sim, store)
    await sim.external_change("temperature_setpoint", 26)
    await sim.inject_fault(FaultType.DELAY_APPLY, "cabin.set_temperature", 1)
    run2 = await harness.create_run(f"f04-{uuid.uuid4()}", "把空调设为 23 度", "test", True)
    assert (await sim.read_state(None)).state["temperature_setpoint"] == 23
    assert run2.lifecycle == RunLifecycle.COMPLETED

    await _reset(harness, sim, store)
    await sim.external_change("navigation_muted", True)
    run3 = await harness.create_run(
        f"c08-{uuid.uuid4()}", "导航有画面但没有声音，帮我检查一下，不要重启车机。", "test", True
    )
    assert run3.route_type and run3.route_type.value == "MULTI_AGENT"
    assert (await sim.read_state(None)).state["navigation_muted"] is False

    await _reset(harness, sim, store)
    props.require_confirmation = True
    policy.require_confirmation = True
    waiting = await harness.create_run(f"cancel-{uuid.uuid4()}", "把空调设为 23 度", "test", True)
    assert waiting.lifecycle == RunLifecycle.WAITING_CONFIRMATION
    assert any(a.execution_status == ExecutionStatus.PROPOSED for a in waiting.actions)
    cancelled = await harness.cancel(waiting.run_id)
    assert cancelled.lifecycle == RunLifecycle.CANCELLED
    assert any(a.execution_status == ExecutionStatus.CANCELLED_BEFORE_DISPATCH for a in cancelled.actions)
    assert (await sim.read_state(None)).state["temperature_setpoint"] == 26

    await _reset(harness, sim, store)
    props.require_confirmation = True
    policy.require_confirmation = True
    waiting2 = await harness.create_run(f"reset-{uuid.uuid4()}", "把空调设为 23 度", "test", True)
    assert waiting2.lifecycle == RunLifecycle.WAITING_CONFIRMATION
    await harness.reset_experiment()
    assert store.find(waiting2.run_id).lifecycle == RunLifecycle.CANCELLED
    props.require_confirmation = False
    policy.require_confirmation = False
    nxt = await harness.create_run(f"reset-next-{uuid.uuid4()}", "把空调设为 23 度", "test", True)
    assert nxt.lifecycle == RunLifecycle.COMPLETED
    assert (await sim.read_state(None)).state["temperature_setpoint"] == 23
    sim.stop_clock()


@pytest.mark.asyncio
async def test_multi_agent_trace_and_reviewer(tmp_path) -> None:
    harness, sim, store, *_ = _stack(tmp_path)
    await _reset(harness, sim, store)
    chat = await harness.create_run(None, "你好", "test-chat", True)
    assert chat.route_type and chat.route_type.value == "CHAT"
    assert chat.lifecycle == RunLifecycle.COMPLETED
    assert chat.actions == []

    await _reset(harness, sim, store)
    fast = await harness.create_run(None, "把空调设为 23 度", "test-fast", True)
    assert fast.route_type and fast.route_type.value == "FAST"
    events = store.events_after(fast.run_id, 0)
    assert not any(e.type in {"PLAN_DRAFT", "REVIEW_RESULT"} for e in events)

    await _reset(harness, sim, store)
    multi = await harness.create_run(
        None,
        "后排要休息，把座舱调整舒服一点；媒体声音调低，但保留导航提示，不要开窗。",
        "test-multi",
        True,
    )
    assert multi.route_type and multi.route_type.value == "MULTI_AGENT"
    events = store.events_after(multi.run_id, 0)
    types = {e.type for e in events}
    assert {"TASK_SPEC", "PLAN_DRAFT", "REVIEW_RESULT"} <= types
    assert not any(str(a.capability_id).startswith("window.") for a in multi.actions)

    spec = TaskSpec(
        goals=[{"type": "window_position", "window": "front_left", "position": 50}],
        constraints=[{"type": "no_window"}],
        allowed_capabilities=["window.set_position"],
    )
    draft = PlanDraft(actions=[{"capability_id": "window.set_position", "params": {"window": "front_left", "position": 50}}])
    review = MultiAgentSupport.review(spec, draft, "fake")
    assert review.decision == ReviewDecision.REJECT
    sim.stop_clock()


@pytest.mark.asyncio
async def test_to_view_dual_writes_camel_case(tmp_path) -> None:
    harness, sim, store, *_ = _stack(tmp_path)
    await _reset(harness, sim, store)
    run = await harness.create_run(None, "把空调设为 23 度", "test", True)
    view = harness.to_view(run)
    assert view["actions"]
    action = view["actions"][0]
    assert "action_id" in action and "actionId" in action
    assert action["actionId"] == action["action_id"]
    assert "capabilityId" in action
    if view["criteria"]:
        criterion = view["criteria"][0]
        assert "criterion_id" in criterion and "criterionId" in criterion
    sim.stop_clock()
