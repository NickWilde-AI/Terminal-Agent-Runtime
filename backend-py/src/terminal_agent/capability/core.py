"""Capability schemas and deterministic effects used by the runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

WINDOWS = ["front_left", "front_right", "rear_left", "rear_right"]
ROUTE_PREFERENCES = ["fastest", "shortest", "avoid_highway", "avoid_congestion", "less_toll", "less_detour"]


@dataclass(frozen=True)
class CapabilityDefinition:
    id: str
    write: bool
    domains: set[str]
    properties: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    code: str | None = None
    message: str | None = None
    definition: CapabilityDefinition | None = None


def _integer(lo: int, hi: int) -> dict[str, Any]:
    return {"type": "integer", "minimum": lo, "maximum": hi}


def _bool() -> dict[str, Any]:
    return {"type": "boolean"}


def _str(max_length: int, enum: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "string", "maxLength": max_length}
    if enum is not None:
        result["enum"] = enum
    return result


class CapabilityRegistry:
    VERSION = "capabilities-v4"

    def __init__(self) -> None:
        self.capabilities: dict[str, CapabilityDefinition] = {}
        self._register()

    def _add(self, id_: str, write: bool, domain: str, properties: dict[str, dict[str, Any]]) -> None:
        self.capabilities[id_] = CapabilityDefinition(id_, write, {domain}, properties)

    def _alias(self, alias: str, target: str) -> None:
        self.capabilities[alias] = self.capabilities[target]

    def _register(self) -> None:
        self._add("device.get_state", False, "CABIN", {})
        self._add("climate.set_power", True, "CABIN", {"value": _bool()})
        self._add("climate.set_temperature", True, "CABIN", {"value": _integer(16, 30)})
        self._add("climate.set_fan", True, "CABIN", {"value": _integer(1, 3)})
        self._add(
            "window.set_position", True, "CABIN", {"window": _str(120, WINDOWS + ["all"]), "position": _integer(0, 100)}
        )
        self._add("media.play", True, "MEDIA", {"artist": _str(80)})
        self._add("media.pause", True, "MEDIA", {})
        self._add("media.set_volume", True, "MEDIA", {"value": _integer(0, 10)})
        self._add("navigation.start", True, "NAVIGATION", {"destination": _str(120)})
        for name in (
            "stop",
            "pause",
            "resume",
            "navigate_home",
            "navigate_company",
            "query_eta",
            "query_status",
            "query_waypoints",
        ):
            self._add(f"navigation.{name}", True, "NAVIGATION", {})
        self._add("navigation.add_waypoint", True, "NAVIGATION", {"name": _str(120)})
        self._add("navigation.remove_waypoint", True, "NAVIGATION", {"name": _str(120)})
        self._add("navigation.set_preference", True, "NAVIGATION", {"value": _str(120, ROUTE_PREFERENCES)})
        self._add("navigation.set_home", True, "NAVIGATION", {"place": _str(120)})
        self._add("navigation.set_company", True, "NAVIGATION", {"place": _str(120)})
        self._add("navigation.set_prompt_enabled", True, "NAVIGATION", {"value": _bool()})
        self._add("navigation.set_volume", True, "NAVIGATION", {"value": _integer(0, 10)})
        self._add("navigation.set_muted", True, "NAVIGATION", {"value": _bool()})
        self._add("life.search_shops", True, "LIFE", {"keyword": _str(80)})
        self._add("life.enter_shop", True, "LIFE", {"shop_name": _str(80)})
        self._add("life.add_to_cart", True, "LIFE", {"item": _str(80)})
        self._add("life.go_to_checkout", True, "LIFE", {})
        self._add("life.close", True, "LIFE", {})
        self._add("iot.light.set_power", True, "IOT", {"value": _bool()})
        for alias, target in {
            "cabin.set_temperature": "climate.set_temperature",
            "cabin.set_fan": "climate.set_fan",
            "device.read_state": "device.get_state",
            "navigation.set_route": "navigation.start",
            "navigation.exit": "navigation.stop",
            "navigation.nav_exit": "navigation.stop",
            "light.set_power": "iot.light.set_power",
        }.items():
            self._alias(alias, target)

    def get(self, id_: str) -> CapabilityDefinition | None:
        return self.capabilities.get(id_)

    def canonical(self, id_: str) -> str:
        return self.capabilities[id_].id if id_ in self.capabilities else id_

    def validate(self, id_: str, params: dict[str, Any] | None) -> ValidationResult:
        definition = self.get(id_)
        if definition is None:
            return ValidationResult(False, "UNKNOWN_CAPABILITY", f"未注册能力: {id_}")
        if params is None:
            return ValidationResult(False, "SCHEMA", "参数必须是对象")
        if set(params) != set(definition.properties):
            return ValidationResult(False, "SCHEMA", f"参数字段必须为 {set(definition.properties)}")
        for key, schema in definition.properties.items():
            value, kind = params[key], schema["type"]
            ok = False
            if kind == "integer":
                ok = (
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and schema["minimum"] <= value <= schema["maximum"]
                )
            elif kind == "boolean":
                ok = isinstance(value, bool)
            elif kind == "string":
                ok = isinstance(value, str) and bool(value.strip()) and len(value) <= schema.get("maxLength", 120)
                ok = ok and ("enum" not in schema or value in schema["enum"])
            if not ok:
                return ValidationResult(False, "SCHEMA", f"非法参数: {key}，不截断执行")
        return ValidationResult(True, definition=definition)


def expected_effects(id_: str, params: dict[str, Any]) -> dict[str, Any]:
    value = params.get("value")
    fixed = {
        "climate.set_power": {"climate_power": value},
        "climate.set_temperature": {"temperature_setpoint": value},
        "cabin.set_temperature": {"temperature_setpoint": value},
        "climate.set_fan": {"fan_level": value},
        "cabin.set_fan": {"fan_level": value},
        "media.play": {"media_playing": True, "media_artist": params.get("artist")},
        "media.pause": {"media_playing": False},
        "media.set_volume": {"media_volume": value},
        "navigation.start": {
            "navigation_active": True,
            "navigation_destination": params.get("destination"),
            "navigation_paused": False,
        },
        "navigation.set_route": {
            "navigation_active": True,
            "navigation_destination": params.get("destination"),
            "navigation_paused": False,
        },
        "navigation.stop": {"navigation_active": False, "navigation_paused": False},
        "navigation.exit": {"navigation_active": False, "navigation_paused": False},
        "navigation.nav_exit": {"navigation_active": False, "navigation_paused": False},
        "navigation.pause": {"navigation_paused": True},
        "navigation.resume": {"navigation_paused": False},
        "navigation.set_preference": {"navigation_preference": value},
        "navigation.navigate_home": {"navigation_active": True, "navigation_paused": False},
        "navigation.navigate_company": {"navigation_active": True, "navigation_paused": False},
        "navigation.set_home": {"navigation_home": params.get("place")},
        "navigation.set_company": {"navigation_company": params.get("place")},
        "navigation.set_prompt_enabled": {"prompt_enabled": value},
        "navigation.set_volume": {"navigation_volume": value},
        "navigation.set_muted": {"navigation_muted": value},
        "life.search_shops": {"life_session_active": True, "life_phase": "shop_list"},
        "life.enter_shop": {"life_session_active": True, "life_phase": "in_shop"},
        "life.add_to_cart": {"life_session_active": True, "life_phase": "in_shop"},
        "life.go_to_checkout": {"life_session_active": True, "life_phase": "checkout"},
        "life.close": {"life_session_active": False, "life_phase": "idle"},
        "iot.light.set_power": {"light_power": value},
        "light.set_power": {"light_power": value},
    }
    if id_ == "window.set_position":
        return {f"window_{w}": params["position"] for w in WINDOWS if params["window"] in ("all", w)}
    return fixed.get(id_, {})


def eq(a: Any, b: Any) -> bool:
    if (
        isinstance(a, (int, float))
        and not isinstance(a, bool)
        and isinstance(b, (int, float))
        and not isinstance(b, bool)
    ):
        return float(a) == float(b)
    return a == b


def effects_match(id_: str, params: dict[str, Any], state: dict[str, Any]) -> bool:
    expected = expected_effects(id_, params)
    if expected:
        return all(eq(state.get(k), v) for k, v in expected.items())
    if id_ == "navigation.add_waypoint":
        return params.get("name") in state.get("navigation_waypoints", [])
    if id_ == "navigation.remove_waypoint":
        return params.get("name") not in state.get("navigation_waypoints", [])
    query = {
        "navigation.query_eta": "eta",
        "navigation.query_status": "status",
        "navigation.query_waypoints": "waypoints",
    }
    return id_ in query and state.get("last_nav_query_type") == query[id_]
