"""Contract tests for cancel/dispatch races and schema parity with Java."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from terminal_agent.capability.core import CapabilityRegistry
from terminal_agent.contracts import ExecutionStatus, GoalOutcome, RunLifecycle, RunRecord, now
from terminal_agent.device.simulator import DeviceSimulator
from terminal_agent.model.fake import FakeModelAdapter
from terminal_agent.persistence.sqlite import SqlitePersistence
from terminal_agent.persistence.store import InMemoryRunStore
from terminal_agent.policy.engine import PolicyEngine
from terminal_agent.runtime.executor import CapabilityExecutor
from terminal_agent.runtime.harness import HarnessService
from terminal_agent.runtime.support import RuntimeSettings, TaskBinder
from terminal_agent.runtime.task_binder import action_for as binder_action_for
from terminal_agent.runtime.verifier import Verifier


def _stack(tmp_path):
    registry = CapabilityRegistry()
    sim = DeviceSimulator(registry)
    store = InMemoryRunStore(str(tmp_path / "events"))
    policy = PolicyEngine(registry, False)
    executor = CapabilityExecutor(sim, registry, policy, store, fresh_window_ms=2000)
    verifier = Verifier(sim)
    persistence = SqlitePersistence(store, sim, str(tmp_path / "db.sqlite"), enabled=False)
    harness = HarnessService(
        store, sim, FakeModelAdapter(), TaskBinder(registry), executor, verifier, persistence, RuntimeSettings()
    )
    sim.start_clock()
    return harness, sim, store, executor, registry


def test_core_registry_accepts_int_like_float() -> None:
    registry = CapabilityRegistry()
    assert registry.validate("climate.set_temperature", {"value": 23}).ok is True
    assert registry.validate("climate.set_temperature", {"value": 23.0}).ok is True
    assert registry.validate("climate.set_temperature", {"value": 23.5}).ok is False
    assert registry.validate("climate.set_temperature", {"value": True}).ok is False


def test_taskbinder_action_for_is_shared() -> None:
    goal = {"type": "cabin_temperature", "value": 23}
    assert TaskBinder.action_for(goal) == binder_action_for(goal)
    assert TaskBinder.action_for(goal)["capability_id"] == "climate.set_temperature"


@pytest.mark.asyncio
async def test_cancel_accepted_blocks_dispatch(tmp_path) -> None:
    harness, sim, store, executor, _ = _stack(tmp_path)
    run = RunRecord(
        run_id="run-cancel",
        request_id="req-cancel",
        device_id=sim.device_id,
        environment_id=sim.environment_id,
        lifecycle=RunLifecycle.RUNNING,
    )
    run.budget.deadline = now() + timedelta(seconds=30)
    store.save(run)
    run.cancel_accepted = True
    action = await executor.execute_write(run, "climate.set_temperature", {"value": 23})
    assert action.execution_status == ExecutionStatus.CANCELLED_BEFORE_DISPATCH
    assert (await sim.read_state(None)).state["temperature_setpoint"] == 26
    sim.stop_clock()


@pytest.mark.asyncio
async def test_cancel_cannot_slip_between_authorize_awaits(tmp_path) -> None:
    """Holding per-run lock across authorize→DISPATCH matches Java synchronized(r)."""
    harness, sim, store, executor, _ = _stack(tmp_path)
    run = RunRecord(
        run_id="run-race",
        request_id="req-race",
        device_id=sim.device_id,
        environment_id=sim.environment_id,
        lifecycle=RunLifecycle.RUNNING,
    )
    run.budget.deadline = now() + timedelta(seconds=30)
    store.save(run)

    original_append = store.append_event
    saw_policy = asyncio.Event()

    async def slow_append(run_obj, type_, payload=None):
        result = await original_append(run_obj, type_, payload)
        if type_ == "POLICY":
            saw_policy.set()
            await asyncio.sleep(0.05)
        return result

    store.append_event = slow_append  # type: ignore[method-assign]

    async def cancel_during_authorize() -> None:
        await saw_policy.wait()
        # Must block on run_lock until DISPATCH reservation completes.
        await harness.cancel(run.run_id)

    cancel_task = asyncio.create_task(cancel_during_authorize())
    action = await executor.execute_write(run, "climate.set_temperature", {"value": 23})
    await cancel_task

    # Either cancel won before authorize lock, or dispatch reserved first then cancel finished.
    # Never: cancel_accepted observed mid-authorize yet still apply without DISPATCH reservation.
    assert run.lifecycle == RunLifecycle.CANCELLED
    if action.execution_status == ExecutionStatus.CANCELLED_BEFORE_DISPATCH:
        assert (await sim.read_state(None)).state["temperature_setpoint"] == 26
    else:
        # Dispatch won the race; in-flight write may still apply (Java-equivalent).
        assert action.execution_status in {
            ExecutionStatus.APPLIED,
            ExecutionStatus.ACKNOWLEDGED,
            ExecutionStatus.NOT_APPLIED,
            ExecutionStatus.UNKNOWN,
        }
        assert run.in_flight_action_id is None or action.execution_status == ExecutionStatus.UNKNOWN
    sim.stop_clock()


@pytest.mark.asyncio
async def test_finish_is_first_wins(tmp_path) -> None:
    harness, sim, store, *_ = _stack(tmp_path)
    run = RunRecord(
        run_id="run-finish",
        request_id="req-finish",
        device_id=sim.device_id,
        environment_id=sim.environment_id,
        lifecycle=RunLifecycle.RUNNING,
    )
    store.save(run)

    async def finish_a() -> None:
        await harness._finish(run, RunLifecycle.CANCELLED, "USER_CANCEL", "a", GoalOutcome.UNKNOWN)

    async def finish_b() -> None:
        await harness._finish(run, RunLifecycle.TIMED_OUT, "TIMED_OUT", "b", GoalOutcome.UNKNOWN)

    await asyncio.gather(finish_a(), finish_b())
    assert run.lifecycle in {RunLifecycle.CANCELLED, RunLifecycle.TIMED_OUT}
    # Exactly one terminal write — second must no-op.
    finished = [e for e in run.events if e.type == "RUN_FINISHED"]
    assert len(finished) == 1
    sim.stop_clock()


@pytest.mark.asyncio
async def test_fast_path_temperature(tmp_path) -> None:
    harness, sim, *_ = _stack(tmp_path)
    run = await harness.create_run(None, "把空调设为 23 度", "eval", True)
    assert run.lifecycle == RunLifecycle.COMPLETED
    assert run.route_type and run.route_type.value == "FAST"
    assert (await sim.read_state(None)).state["temperature_setpoint"] == 23
    sim.stop_clock()
