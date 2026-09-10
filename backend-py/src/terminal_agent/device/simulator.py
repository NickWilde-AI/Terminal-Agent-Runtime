"""Async local DevicePort implementation with Java-equivalent fault semantics."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from copy import deepcopy
from datetime import timedelta
from typing import Any

from terminal_agent.capability.core import WINDOWS, CapabilityRegistry, expected_effects
from terminal_agent.contracts import ActionRecord, DeviceDomain, StateSnapshot, new_id, now
from terminal_agent.device.port import DeviceException, FaultType


class DeviceSimulator:
    KNOWN_POIS = {
        "东方明珠",
        "虹桥机场",
        "浦东机场",
        "固安",
        "星巴克",
        "加油站",
        "迪士尼",
        "上海游泳馆",
        "浦东美术馆",
        "鼋头渚",
        "灵山大佛",
        "三凤桥",
        "无锡国际会议中心",
        "虹桥幸福里",
        "陆家嘴办公楼",
    }

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self.registry = registry or CapabilityRegistry()
        self._lock = asyncio.Lock()
        self._environment_id = new_id("env")
        self.revision = 1
        self.state: dict[str, Any] = {}
        self.revisions: dict[str, int] = {}
        self.origins: dict[str, dict[str, Any]] = {}
        self.actions_by_id: dict[str, ActionRecord] = {}
        self.actions_by_key: dict[str, ActionRecord] = {}
        self.fault = FaultType.NONE
        self.fault_capability: str | None = None
        self.remaining = 0
        self._persistence: Callable[[dict[str, Any]], Any] = lambda _: None
        self._listeners: list[Callable[[dict[str, Any]], Any]] = []
        self._clock_task: asyncio.Task[None] | None = None
        self._defaults()

    @property
    def device_id(self) -> str:
        return "terminal-1"

    @property
    def environment_id(self) -> str:
        return self._environment_id

    def _defaults(self) -> None:
        self.state = {
            "climate_power": False,
            "temperature_setpoint": 26,
            "cabin_temperature": 27,
            "fan_level": 3,
            "window_open": False,
            "media_volume": 8,
            "media_muted": False,
            "media_playing": False,
            "media_track": None,
            "media_artist": None,
            "navigation_active": True,
            "navigation_destination": None,
            "navigation_paused": False,
            "navigation_waypoints": [],
            "navigation_preference": "fastest",
            "navigation_home": "虹桥幸福里",
            "navigation_company": "陆家嘴办公楼",
            "navigation_eta_minutes": None,
            "last_nav_query_type": None,
            "last_nav_query_result": None,
            "route_points": [],
            "prompt_enabled": True,
            "navigation_volume": 5,
            "navigation_muted": False,
            "route_available": True,
            "focus_available": True,
            "last_prompt_event_id": None,
            "last_prompt_at": None,
            "last_prompt_result": None,
            "last_prompt_navigation_revision": 0,
            "life_session_active": False,
            "life_phase": "idle",
            "life_last_keyword": None,
            "life_last_shop": None,
            "life_last_item": None,
            "light_power": False,
        }
        self.state.update({f"window_{w}": 0 for w in WINDOWS})
        self.revisions = {domain.value: 1 for domain in DeviceDomain}
        self.origins = {}
        self.revision = 1

    def on_persist(self, sink: Callable[[dict[str, Any]], Any]) -> None:
        self._persistence = sink

    def start_clock(self) -> None:
        """Mirror Java SimulatorBean: tick delayed actions ~every 50ms."""
        if self._clock_task and not self._clock_task.done():
            return

        async def _loop() -> None:
            while True:
                try:
                    await self.tick()
                except Exception:
                    pass
                await asyncio.sleep(0.05)

        try:
            self._clock_task = asyncio.create_task(_loop(), name="simulator-clock")
        except RuntimeError:
            self._clock_task = None

    def stop_clock(self) -> None:
        if self._clock_task and not self._clock_task.done():
            self._clock_task.cancel()
        self._clock_task = None

    def add_change_listener(self, listener: Callable[[dict[str, Any]], Any]) -> None:
        self._listeners.append(listener)

    def remove_change_listener(self, listener: Callable[[dict[str, Any]], Any]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def _call(self, fn: Callable[..., Any], value: Any) -> None:
        result = fn(value)
        if inspect.isawaitable(result):
            await result

    def _consume(self, type_: FaultType, capability_id: str | None) -> bool:
        if self.fault != type_ or self.remaining <= 0:
            return False
        if self.fault_capability is not None and not self._same_capability(self.fault_capability, capability_id):
            return False
        self.remaining -= 1
        return True

    def _same_capability(self, a: str | None, b: str | None) -> bool:
        if a == b:
            return True
        return self.registry.canonical(a or "") == self.registry.canonical(b or "")

    async def inject_fault(self, type_: FaultType, capability_id: str | None = None, times: int = 1) -> None:
        if not 1 <= times <= 1000:
            raise ValueError("times must be 1..1000")
        async with self._lock:
            self.fault, self.fault_capability, self.remaining = type_, capability_id, times

    async def clear_fault(self) -> None:
        self.fault, self.remaining = FaultType.NONE, 0

    def _snapshot(self) -> StateSnapshot:
        return StateSnapshot(
            revision=self.revision,
            origins=deepcopy(self.origins),
            device_id=self.device_id,
            environment_id=self.environment_id,
            domain_revisions=dict(self.revisions),
            observed_at=now(),
            state=deepcopy(self.state),
        )

    async def snapshot(self) -> StateSnapshot:
        async with self._lock:
            return self._snapshot()

    async def read_state(self, domains: set[DeviceDomain] | None = None) -> StateSnapshot:
        del domains
        async with self._lock:
            if self._consume(FaultType.READ_FAIL, None):
                raise DeviceException("READ_UNAVAILABLE", "状态读取不可用")
            result = self._snapshot()
            if self._consume(FaultType.STALE_STATE, None):
                result.observed_at = now() - timedelta(seconds=30)
            return result

    async def reset_to_defaults(self) -> None:
        async with self._lock:
            if any(a.status == "QUEUED" for a in self.actions_by_id.values()):
                raise DeviceException("RESET_BUSY", "存在在途动作")
            self._defaults()
            self.actions_by_id.clear()
            self.actions_by_key.clear()
            self.fault, self.remaining = FaultType.NONE, 0
            self._environment_id = new_id("env")
            await self._commit()

    async def force_new_environment(self) -> None:
        async with self._lock:
            self.actions_by_id.clear()
            self.actions_by_key.clear()
            self.fault, self.remaining = FaultType.NONE, 0
            self._environment_id = new_id("env")
            self.revision += 1
            await self._commit()

    def _precondition(self, action: ActionRecord) -> str | None:
        if self.environment_id != action.environment_id:
            return "ENVIRONMENT_MISMATCH"
        if action.deadline and now() > action.deadline:
            return "DEADLINE_EXCEEDED"
        definition = self.registry.get(action.capability_id)
        for domain in definition.domains if definition else set():
            if domain in action.expected_revisions and action.expected_revisions[domain] != self.revisions.get(domain):
                return "REVISION_CONFLICT"
        return None

    async def apply_write(
        self,
        action_id: str,
        idempotency_key: str,
        capability_id: str,
        params: dict[str, Any],
        environment_id: str,
        deadline: Any,
        expected_revisions: dict[str, int] | None,
        run_id: str | None = None,
        goal_version: int = 0,
    ) -> ActionRecord:
        async with self._lock:
            old = self.actions_by_key.get(idempotency_key)
            if old:
                if old.params != params or old.capability_id != capability_id or old.environment_id != environment_id:
                    raise DeviceException("IDEMPOTENCY_CONFLICT", "同键参数或环境不一致")
                return old
            action = ActionRecord(
                action_id=action_id,
                idempotency_key=idempotency_key,
                capability_id=capability_id,
                params=dict(params),
                environment_id=environment_id,
                deadline=deadline,
                expected_revisions=dict(expected_revisions or {}),
                run_id=run_id,
                goal_version=goal_version,
            )
            self.actions_by_id[action_id] = action
            self.actions_by_key[idempotency_key] = action
            validation, invalid = self.registry.validate(capability_id, params), self._precondition(action)
            if not validation.ok or invalid:
                return await self._finish(action, "NOT_APPLIED", invalid or validation.code or "SCHEMA")
            if self._consume(FaultType.REJECT, capability_id):
                return await self._finish(action, "NOT_APPLIED", "DEVICE_REJECTED")
            if self._consume(FaultType.ACK_NOT_APPLIED, capability_id):
                return await self._finish(action, "NOT_APPLIED", "ACK_NOT_APPLIED")
            if self._consume(FaultType.DELAY_APPLY, capability_id):
                action.apply_after_ms = int(time.time() * 1000) + 100
                action.message = "ACCEPTED"
                await self._commit()
                return action
            if self._consume(FaultType.TOOL_TIMEOUT, capability_id):
                action.message = "TIMEOUT"
                await self._commit()
                raise DeviceException("RESPONSE_LOST", "设备响应超时", action_id)
            await self._apply(action)
            if self._consume(FaultType.APPLIED_RESPONSE_LOST, capability_id):
                raise DeviceException("RESPONSE_LOST", "响应丢失，执行终局需查询", action_id)
            return action

    def _navigation_precheck(self, cap: str, params: dict[str, Any]) -> str | None:
        if cap in ("navigation.start", "navigation.set_route"):
            return None if self._poi_resolvable(str(params.get("destination", "")).strip()) else "SEARCH_NO_CANDIDATE"
        if cap == "navigation.navigate_home":
            return None if self.state["navigation_home"] is not None else "NEED_SET_HOME"
        if cap == "navigation.navigate_company":
            return None if self.state["navigation_company"] is not None else "NEED_SET_COMPANY"
        if cap in ("navigation.pause", "navigation.resume"):
            return None if self.state["navigation_active"] else "NOT_NAVIGATING"
        if cap == "navigation.add_waypoint":
            if not self.state["navigation_active"] or self.state["navigation_destination"] is None:
                return "NO_ACTIVE_DESTINATION"
            return None if self._poi_resolvable(str(params.get("name", "")).strip()) else "SEARCH_NO_CANDIDATE"
        if cap == "navigation.remove_waypoint":
            if not self.state["navigation_active"]:
                return "NOT_NAVIGATING"
            return None if params.get("name") in self.state["navigation_waypoints"] else "WAYPOINT_NOT_FOUND"
        return None

    def _poi_resolvable(self, name: str) -> bool:
        return bool(name) and (
            name in self.KNOWN_POIS
            or name in {self.state.get("navigation_home"), self.state.get("navigation_company"), "家", "公司"}
        )

    async def _apply(self, action: ActionRecord) -> None:
        invalid = self._precondition(action)
        if invalid:
            await self._finish(action, "NOT_APPLIED", invalid)
            return
        cap = self.registry.canonical(action.capability_id)
        nav_fail = self._navigation_precheck(cap, action.params)
        if nav_fail:
            await self._finish(action, "NOT_APPLIED", nav_fail)
            return
        updates = dict(expected_effects(cap, action.params))
        if cap == "media.play":
            updates["media_track"] = "公开占位曲目 · 无音频"
        self._navigation_effects(cap, action.params, updates)
        self._life_effects(cap, action.params, updates)
        self._change(updates, "AGENT_ACTION", action)
        action.revision = self.revision
        await self._finish(action, "APPLIED", "OK")

    def _navigation_effects(self, cap: str, p: dict[str, Any], u: dict[str, Any]) -> None:
        if cap in ("navigation.start", "navigation.set_route"):
            u.update(
                navigation_active=True,
                navigation_destination=p["destination"],
                navigation_paused=False,
                navigation_waypoints=[],
                route_points=[[-2, 0], [-1, 1], [1, 1], [2, 2]],
                navigation_eta_minutes=12,
            )
            self._clear_nav_query(u)
            self._close_life(u)
        elif cap in ("navigation.stop", "navigation.exit", "navigation.nav_exit"):
            u.update(
                navigation_active=False,
                navigation_destination=None,
                navigation_paused=False,
                navigation_waypoints=[],
                route_points=[],
                navigation_eta_minutes=None,
            )
            self._clear_nav_query(u)
        elif cap in ("navigation.add_waypoint", "navigation.remove_waypoint"):
            points = list(self.state["navigation_waypoints"])
            name = str(p["name"])
            if cap.endswith("add_waypoint") and name not in points:
                points.append(name)
            if cap.endswith("remove_waypoint") and name in points:
                points.remove(name)
            u.update(
                navigation_waypoints=points,
                navigation_eta_minutes=12 + len(points) * 8,
                navigation_destination=self.state["navigation_destination"],
                navigation_active=True,
            )
        elif cap in ("navigation.navigate_home", "navigation.navigate_company"):
            key = "navigation_home" if cap.endswith("home") else "navigation_company"
            route = [[-2, 0], [0, 1], [2, 2]] if cap.endswith("home") else [[-1, 0], [1, 1], [2, 0]]
            u.update(
                navigation_active=True,
                navigation_destination=self.state[key],
                navigation_paused=False,
                navigation_waypoints=[],
                route_points=route,
                navigation_eta_minutes=12,
            )
            self._clear_nav_query(u)
            self._close_life(u)
        elif cap == "navigation.query_eta":
            u.update(
                last_nav_query_type="eta",
                last_nav_query_result=(
                    f"预计剩余 {self.state.get('navigation_eta_minutes', 15)} 分钟到达 {self.state['navigation_destination']}"
                    if self.state["navigation_active"]
                    else "当前未在导航中，无法提供 ETA"
                ),
            )
        elif cap == "navigation.query_status":
            if self.state["navigation_active"]:
                paused = "（已暂停）" if self.state["navigation_paused"] else ""
                result = f"导航中，目的地 {self.state['navigation_destination']}{paused}，偏好 {self.state['navigation_preference']}"
            else:
                result = "当前未在导航"
            u.update(last_nav_query_type="status", last_nav_query_result=result)
        elif cap == "navigation.query_waypoints":
            points = self.state["navigation_waypoints"]
            u.update(
                last_nav_query_type="waypoints",
                last_nav_query_result="途经点：" + "、".join(points) if points else "当前无途经点",
            )

    def _life_effects(self, cap: str, p: dict[str, Any], u: dict[str, Any]) -> None:
        if cap == "life.search_shops":
            u.update(life_session_active=True, life_phase="shop_list", life_last_keyword=p["keyword"])
        elif cap == "life.enter_shop":
            u.update(life_session_active=True, life_phase="in_shop", life_last_shop=p["shop_name"])
        elif cap == "life.add_to_cart":
            u.update(life_session_active=True, life_phase="in_shop", life_last_item=p["item"])
        elif cap == "life.go_to_checkout":
            u.update(life_session_active=True, life_phase="checkout")
        elif cap == "life.close":
            self._close_life(u)

    @staticmethod
    def _clear_nav_query(u: dict[str, Any]) -> None:
        u.update(last_nav_query_type=None, last_nav_query_result=None)

    @staticmethod
    def _close_life(u: dict[str, Any]) -> None:
        u.update(
            life_session_active=False,
            life_phase="idle",
            life_last_keyword=None,
            life_last_shop=None,
            life_last_item=None,
        )

    def _domain(self, field: str) -> str:
        if field.startswith("media_"):
            return "MEDIA"
        if field.startswith("life_"):
            return "LIFE"
        if field.startswith(("light_", "iot_")):
            return "IOT"
        if field.startswith("last_") or field in ("route_available", "focus_available"):
            return "AUDIO"
        if field.startswith("navigation_") or field in (
            "prompt_enabled",
            "route_points",
            "last_nav_query_type",
            "last_nav_query_result",
        ):
            return "NAVIGATION"
        return "CABIN"

    def _change(self, updates: dict[str, Any], source: str, action: ActionRecord | None) -> None:
        self.revision += 1
        touched: set[str] = set()
        for field, value in updates.items():
            self.state[field] = value
            touched.add(self._domain(field))
            self.origins[field] = {
                "run_id": action.run_id if action else None,
                "action_id": action.action_id if action else None,
                "goal_version": action.goal_version if action else None,
                "environment_id": self.environment_id,
                "revision": self.revision,
                "origin": source,
                "observed_at": now().isoformat(),
            }
        self.state["window_open"] = any(self.state[f"window_{w}"] > 0 for w in WINDOWS)
        for domain in touched:
            self.revisions[domain] = self.revisions.get(domain, 0) + 1

    async def _finish(self, action: ActionRecord, status: str, message: str) -> ActionRecord:
        action.status, action.message, action.finished_at = status, message, now()
        await self._commit()
        return action

    async def query_action(self, action_id: str) -> ActionRecord | None:
        async with self._lock:
            return self.actions_by_id.get(action_id)

    async def tick(self) -> None:
        async with self._lock:
            changed = False
            for action in list(self.actions_by_id.values()):
                if (
                    action.status == "QUEUED"
                    and action.apply_after_ms
                    and int(time.time() * 1000) >= action.apply_after_ms
                ):
                    await self._apply(action)
                    changed = True
            previous = self.state["last_prompt_at"]
            if self.state["navigation_active"] and (
                previous is None or now() - _parse_time(previous) > timedelta(milliseconds=500)
            ):
                self._emit_prompt_event()
                changed = True
            if changed:
                await self._commit()

    def _emit_prompt_event(self) -> None:
        played = (
            self.state["navigation_active"]
            and self.state["prompt_enabled"]
            and not self.state["navigation_muted"]
            and self.state["navigation_volume"] > 0
            and self.state["route_available"]
            and self.state["focus_available"]
        )
        self._change(
            {
                "last_prompt_event_id": new_id("prompt"),
                "last_prompt_at": now().isoformat(),
                "last_prompt_result": "PLAYED" if played else "BLOCKED",
                "last_prompt_navigation_revision": self.revisions["NAVIGATION"],
            },
            "EXTERNAL",
            None,
        )

    async def emit_prompt_event(self) -> None:
        async with self._lock:
            self._emit_prompt_event()
            await self._commit()

    async def apply_initial_state(self, fields: dict[str, Any]) -> None:
        for field, value in (fields or {}).items():
            await self.external_change(field, value)

    async def external_change(self, field: str, value: Any) -> None:
        async with self._lock:
            if field not in self.state:
                raise DeviceException("UNSUPPORTED_FIELD", f"不支持字段 {field}")
            old = self.state[field]
            if isinstance(old, bool) and not isinstance(value, bool):
                raise ValueError("boolean required")
            if isinstance(old, (int, float)) and not isinstance(old, bool) and not isinstance(value, (int, float)):
                raise ValueError("number required")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                lo, hi = 0, 10
                if field.startswith("window_"):
                    hi = 100
                if field == "temperature_setpoint":
                    lo, hi = 16, 30
                if field == "cabin_temperature":
                    lo, hi = -30, 70
                if field == "fan_level":
                    hi = 3
                if field == "navigation_eta_minutes":
                    hi = 600
                if not field.startswith("last_") and (value != int(value) or not lo <= value <= hi):
                    raise ValueError("field out of range")
            updates = {field: value}
            if field == "window_open":
                updates.update({f"window_{w}": 100 if value else 0 for w in WINDOWS})
            self._change(updates, "EXTERNAL", None)
            await self._commit()

    def export_state(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "revision": self.revision,
            "state": deepcopy(self.state),
            "revisions": dict(self.revisions),
            "origins": deepcopy(self.origins),
            "actions": [a.model_dump(mode="json") for a in self.actions_by_id.values()],
        }

    async def restore(self, saved: dict[str, Any]) -> None:
        async with self._lock:
            self._environment_id = saved["environment_id"]
            self.revision = int(saved["revision"])
            self.state = deepcopy(saved["state"])
            self.revisions = {k: int(v) for k, v in saved["revisions"].items()}
            self.origins = deepcopy(saved["origins"])
            self.actions_by_id.clear()
            self.actions_by_key.clear()
            for raw in saved.get("actions", []):
                action = ActionRecord.model_validate(raw)
                self.actions_by_id[action.action_id] = action
                self.actions_by_key[action.idempotency_key] = action

    async def terminate_queued_actions(self) -> None:
        async with self._lock:
            for action in self.actions_by_id.values():
                if action.status == "QUEUED":
                    await self._finish(action, "NOT_APPLIED", "INTERRUPTED_QUEUED")

    def _view(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "environment_id": self.environment_id,
            "revision": self.revision,
            "observed_at": now(),
            "domain_revisions": dict(self.revisions),
            "origins": deepcopy(self.origins),
            "state": deepcopy(self.state),
            "simulation": True,
            "climate": {
                "power": self.state["climate_power"],
                "setpoint": self.state["temperature_setpoint"],
                "cabin_temperature": self.state["cabin_temperature"],
                "fan_level": self.state["fan_level"],
            },
            "windows": {w: self.state[f"window_{w}"] for w in WINDOWS},
            "media": {
                "playing": self.state["media_playing"],
                "track": self.state["media_track"],
                "artist": self.state["media_artist"],
                "volume": self.state["media_volume"],
            },
            "navigation": {
                "active": self.state["navigation_active"],
                "destination": self.state["navigation_destination"],
                "paused": self.state["navigation_paused"],
                "waypoints": self.state["navigation_waypoints"],
                "preference": self.state["navigation_preference"],
                "eta_minutes": self.state["navigation_eta_minutes"],
                "home": self.state["navigation_home"],
                "company": self.state["navigation_company"],
                "prompt_enabled": self.state["prompt_enabled"],
                "volume": self.state["navigation_volume"],
                "route_points": self.state["route_points"],
                "last_query": self.state["last_nav_query_result"],
            },
            "life": {
                "session_active": self.state["life_session_active"],
                "phase": self.state["life_phase"],
                "last_keyword": self.state["life_last_keyword"],
                "last_shop": self.state["life_last_shop"],
                "last_item": self.state["life_last_item"],
            },
        }

    async def view(self) -> dict[str, Any]:
        async with self._lock:
            return self._view()

    async def _commit(self) -> None:
        await self._call(self._persistence, self.export_state())
        view = self._view()
        for listener in list(self._listeners):
            await self._call(listener, view)


def _parse_time(value: Any):
    from datetime import datetime

    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
