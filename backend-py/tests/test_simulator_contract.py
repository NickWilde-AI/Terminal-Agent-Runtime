"""Port of Java SimulatorContractTest."""

from __future__ import annotations

from datetime import timedelta

import pytest

from terminal_agent.capability.core import CapabilityRegistry
from terminal_agent.contracts import now
from terminal_agent.device.port import DeviceException, FaultType
from terminal_agent.device.simulator import DeviceSimulator


async def _write(sim: DeviceSimulator, action_id: str, cap: str, params: dict):
    snap = await sim.snapshot()
    return await sim.apply_write(
        action_id,
        action_id,
        cap,
        params,
        sim.environment_id,
        now() + timedelta(seconds=5),
        snap.domain_revisions,
        "run",
        1,
    )


@pytest.mark.asyncio
async def test_windows_are_independent_and_attributed() -> None:
    sim = DeviceSimulator()
    await _write(sim, "a", "window.set_position", {"window": "front_left", "position": 50})
    snap = await sim.snapshot()
    assert snap.state["window_front_left"] == 50
    assert snap.state["window_front_right"] == 0
    assert snap.origins["window_front_left"]["action_id"] == "a"


@pytest.mark.asyncio
async def test_ack_does_not_change_geometry() -> None:
    sim = DeviceSimulator()
    await sim.inject_fault(FaultType.ACK_NOT_APPLIED, "window.set_position", 1)
    record = await _write(sim, "a", "window.set_position", {"window": "front_left", "position": 100})
    assert record.status == "NOT_APPLIED"
    assert (await sim.snapshot()).state["window_front_left"] == 0


@pytest.mark.asyncio
async def test_lost_response_keeps_original_record() -> None:
    sim = DeviceSimulator()
    await sim.inject_fault(FaultType.APPLIED_RESPONSE_LOST, "media.set_volume", 1)
    with pytest.raises(DeviceException):
        await _write(sim, "a", "media.set_volume", {"value": 2})
    assert (await sim.query_action("a")).status == "APPLIED"
    rev = (await sim.snapshot()).revision
    await _write(sim, "a", "media.set_volume", {"value": 2})
    assert (await sim.snapshot()).revision == rev


@pytest.mark.asyncio
async def test_same_key_different_params_rejected() -> None:
    sim = DeviceSimulator()
    await _write(sim, "a", "media.set_volume", {"value": 2})
    with pytest.raises(DeviceException):
        await _write(sim, "a", "media.set_volume", {"value": 3})


@pytest.mark.asyncio
async def test_delayed_action_rechecks_external_revision() -> None:
    sim = DeviceSimulator()
    await sim.inject_fault(FaultType.DELAY_APPLY, "media.set_volume", 1)
    record = await _write(sim, "a", "media.set_volume", {"value": 2})
    await sim.external_change("media_volume", 9)
    record.apply_after_ms = 1
    await sim.tick()
    assert record.status == "NOT_APPLIED"
    snap = await sim.snapshot()
    assert snap.state["media_volume"] == 9
    assert snap.origins["media_volume"]["origin"] == "EXTERNAL"


@pytest.mark.asyncio
async def test_setpoint_never_changes_cabin_temperature() -> None:
    sim = DeviceSimulator()
    await _write(sim, "a", "climate.set_temperature", {"value": 23})
    snap = await sim.snapshot()
    assert snap.state["cabin_temperature"] == 27
    assert snap.state["climate_power"] is False


def test_schema_rejects_unknown_fields_and_bad_values() -> None:
    registry = CapabilityRegistry()
    assert registry.validate("window.set_position", {"window": "all", "position": 101}).ok is False
    assert registry.validate("media.pause", {"value": True}).ok is False
    assert registry.validate("climate.set_power", {"value": "true"}).ok is False
    assert registry.validate("climate.set_temperature", {"value": 23.5}).ok is False
    assert registry.validate("climate.set_temperature", {"value": 23.0}).ok is True


@pytest.mark.asyncio
async def test_old_environment_cannot_apply() -> None:
    sim = DeviceSimulator()
    env = sim.environment_id
    await sim.force_new_environment()
    record = await sim.apply_write(
        "a", "a", "climate.set_power", {"value": True}, env, now() + timedelta(seconds=1), {}
    )
    assert record.status == "NOT_APPLIED"
    assert (await sim.snapshot()).state["climate_power"] is False
