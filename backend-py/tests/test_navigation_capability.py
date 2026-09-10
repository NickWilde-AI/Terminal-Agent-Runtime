"""Port of Java NavigationCapabilityTest."""

from __future__ import annotations

from datetime import timedelta

import pytest

from terminal_agent.agent.contracts import StateSnapshot
from terminal_agent.capability.core import CapabilityRegistry
from terminal_agent.contracts import now
from terminal_agent.device.simulator import DeviceSimulator
from terminal_agent.runtime.goal_compiler import GoalCompiler


async def _write(sim: DeviceSimulator, action_id: str, key: str, cap: str, params: dict):
    return await sim.apply_write(
        action_id, key, cap, params, sim.environment_id, now() + timedelta(seconds=5), {}, "run", 1
    )


def test_registry_exposes_nav_life_iot() -> None:
    registry = CapabilityRegistry()
    assert registry.get("navigation.start") is not None
    assert registry.get("navigation.add_waypoint") is not None
    assert registry.get("navigation.query_eta") is not None
    assert registry.get("navigation.navigate_home") is not None
    assert registry.get("life.search_shops") is not None
    assert registry.get("life.close") is not None
    assert registry.get("iot.light.set_power") is not None
    assert registry.canonical("navigation.set_route") == "navigation.start"
    assert CapabilityRegistry.VERSION == "capabilities-v4"
    assert registry.module_ids() == ["terminal", "iot"]
    assert registry.get("climate.set_temperature").description


@pytest.mark.asyncio
async def test_set_route_and_unknown_poi() -> None:
    sim = DeviceSimulator()
    ok = await _write(sim, "a1", "k1", "navigation.start", {"destination": "东方明珠"})
    assert ok.status == "APPLIED"
    state = (await sim.read_state(None)).state
    assert state["navigation_active"] is True
    assert state["navigation_destination"] == "东方明珠"
    bad = await _write(sim, "a2", "k2", "navigation.start", {"destination": "火星基地999"})
    assert bad.status == "NOT_APPLIED"
    assert bad.message == "SEARCH_NO_CANDIDATE"


@pytest.mark.asyncio
async def test_waypoint_keeps_destination() -> None:
    sim = DeviceSimulator()
    await _write(sim, "a1", "k1", "navigation.start", {"destination": "虹桥机场"})
    wp = await _write(sim, "a2", "k2", "navigation.add_waypoint", {"name": "星巴克"})
    assert wp.status == "APPLIED"
    state = (await sim.read_state(None)).state
    assert state["navigation_destination"] == "虹桥机场"
    assert "星巴克" in state["navigation_waypoints"]


@pytest.mark.asyncio
async def test_add_waypoint_without_destination_fails() -> None:
    sim = DeviceSimulator()
    wp = await _write(sim, "a1", "k1", "navigation.add_waypoint", {"name": "星巴克"})
    assert wp.status == "NOT_APPLIED"
    assert wp.message == "NO_ACTIVE_DESTINATION"


@pytest.mark.asyncio
async def test_go_home_and_company() -> None:
    sim = DeviceSimulator()
    await _write(sim, "a1", "k1", "navigation.navigate_home", {})
    assert (await sim.read_state(None)).state["navigation_destination"] == "虹桥幸福里"
    await _write(sim, "a2", "k2", "navigation.navigate_company", {})
    assert (await sim.read_state(None)).state["navigation_destination"] == "陆家嘴办公楼"


@pytest.mark.asyncio
async def test_life_stubs_and_nav_interrupts_life() -> None:
    sim = DeviceSimulator()
    search = await _write(sim, "a1", "k1", "life.search_shops", {"keyword": "咖啡"})
    assert search.status == "APPLIED"
    assert (await sim.read_state(None)).state["life_session_active"] is True
    await _write(sim, "a2", "k2", "navigation.start", {"destination": "东方明珠"})
    state = (await sim.read_state(None)).state
    assert state["navigation_active"] is True
    assert state["life_session_active"] is False
    assert state["life_phase"] == "idle"


def test_compiler_nav_life_and_iot_routes() -> None:
    go = GoalCompiler.compile("去东方明珠", None, [])
    assert go.route_hint == "FAST"
    assert go.fast_action["capability_id"] == "navigation.start"

    multi = GoalCompiler.compile("回家途经加油站", None, [])
    assert multi.route_hint == "MULTI_AGENT"
    assert any(g.get("type") == "nav_home" for g in multi.goals)
    assert any(g.get("type") == "nav_add_waypoint" and g.get("name") == "加油站" for g in multi.goals)

    snap = StateSnapshot(state={"navigation_active": True, "navigation_destination": None})
    clarify = GoalCompiler.compile("加个途经点星巴克", snap, [])
    assert clarify.route_hint == "CLARIFY"

    checkout = GoalCompiler.compile("去结算", None, [])
    assert checkout.route_hint == "FAST"
    assert checkout.fast_action["capability_id"] == "life.go_to_checkout"

    food = GoalCompiler.compile("点外卖咖啡", None, [])
    assert food.fast_action["capability_id"] == "life.search_shops"

    roadside = GoalCompiler.compile(
        "顺路咖啡", StateSnapshot(state={"navigation_active": True, "navigation_destination": "东方明珠"}), []
    )
    assert roadside.fast_action["capability_id"] == "navigation.add_waypoint"

    light = GoalCompiler.compile("打开灯", None, [])
    assert light.fast_action["capability_id"] == "iot.light.set_power"
