"""Product predicates independent of model-written criteria."""

from __future__ import annotations

from typing import Any

from terminal_agent.capability.terminal_module import WINDOWS


def expected(cap_id: str, params: dict[str, Any]) -> dict[str, Any]:
    v = params.get("value")
    match cap_id:
        case "climate.set_power":
            return {"climate_power": v}
        case "climate.set_temperature" | "cabin.set_temperature":
            return {"temperature_setpoint": v}
        case "climate.set_fan" | "cabin.set_fan":
            return {"fan_level": v}
        case "window.set_position":
            m: dict[str, Any] = {}
            for w in WINDOWS:
                if params.get("window") == "all" or params.get("window") == w:
                    m[f"window_{w}"] = params.get("position")
            return m
        case "media.play":
            return {"media_playing": True, "media_artist": params.get("artist")}
        case "media.pause":
            return {"media_playing": False}
        case "media.set_volume":
            return {"media_volume": v}
        case "navigation.start" | "navigation.set_route":
            return {
                "navigation_active": True,
                "navigation_destination": params.get("destination"),
                "navigation_paused": False,
            }
        case "navigation.stop" | "navigation.exit" | "navigation.nav_exit":
            return {"navigation_active": False, "navigation_paused": False}
        case "navigation.pause":
            return {"navigation_paused": True}
        case "navigation.resume":
            return {"navigation_paused": False}
        case "navigation.set_preference":
            return {"navigation_preference": v}
        case "navigation.navigate_home":
            return {"navigation_active": True, "navigation_paused": False}
        case "navigation.navigate_company":
            return {"navigation_active": True, "navigation_paused": False}
        case "navigation.set_home":
            return {"navigation_home": params.get("place")}
        case "navigation.set_company":
            return {"navigation_company": params.get("place")}
        case "navigation.set_prompt_enabled":
            return {"prompt_enabled": v}
        case "navigation.set_volume":
            return {"navigation_volume": v}
        case "navigation.set_muted":
            return {"navigation_muted": v}
        case "life.search_shops":
            return {"life_session_active": True, "life_phase": "shop_list"}
        case "life.enter_shop":
            return {"life_session_active": True, "life_phase": "in_shop"}
        case "life.add_to_cart":
            return {"life_session_active": True, "life_phase": "in_shop"}
        case "life.go_to_checkout":
            return {"life_session_active": True, "life_phase": "checkout"}
        case "life.close":
            return {"life_session_active": False, "life_phase": "idle"}
        case "iot.light.set_power" | "light.set_power":
            return {"light_power": v}
        case _:
            return {}


def eq(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return float(a) == float(b)
    return bool(a == b)


def matches(cap_id: str, params: dict[str, Any], state: dict[str, Any]) -> bool:
    exp = expected(cap_id, params)
    if not exp:
        match cap_id:
            case "navigation.add_waypoint":
                waypoints = state.get("navigation_waypoints")
                return isinstance(waypoints, list) and params.get("name") in waypoints
            case "navigation.remove_waypoint":
                waypoints = state.get("navigation_waypoints")
                return isinstance(waypoints, list) and params.get("name") not in waypoints
            case "navigation.query_eta":
                return state.get("last_nav_query_type") == "eta"
            case "navigation.query_status":
                return state.get("last_nav_query_type") == "status"
            case "navigation.query_waypoints":
                return state.get("last_nav_query_type") == "waypoints"
            case _:
                return False
    return all(eq(state.get(k), v) for k, v in exp.items())
