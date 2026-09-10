"""Only the product contract creates required predicates; model criteria cannot weaken them."""

from __future__ import annotations

from typing import Any

from terminal_agent.agent.contracts import CompiledTaskCandidate, Criterion, DeviceTask, utcnow
from terminal_agent.capability.effects import expected
from terminal_agent.capability.registry import CapabilityRegistry


def java_str(value: Any) -> str:
    """Mirror Java String.valueOf so null-derived branches stay behaviourally identical."""
    return "null" if value is None else str(value)


def action_params(action: dict[str, Any]) -> dict[str, Any]:
    p = action.get("params")
    return dict(p) if isinstance(p, dict) else {}


def action_for(g: dict[str, Any]) -> dict[str, Any] | None:
    if "capability_id" in g:
        return {"capability_id": g.get("capability_id"), "params": g.get("params", {})}
    type_ = java_str(g.get("type"))
    match type_:
        case "climate_power":
            return {"capability_id": "climate.set_power", "params": {"value": g.get("value")}}
        case "cabin_temperature":
            return {"capability_id": "climate.set_temperature", "params": {"value": g.get("value")}}
        case "cabin_fan":
            return {"capability_id": "climate.set_fan", "params": {"value": g.get("value")}}
        case "window_position":
            return {
                "capability_id": "window.set_position",
                "params": {"window": g.get("window", "all"), "position": g.get("position")},
            }
        case "media_play":
            return {"capability_id": "media.play", "params": {"artist": g.get("artist")}}
        case "media_pause":
            return {"capability_id": "media.pause", "params": {}}
        case "media_volume":
            return {"capability_id": "media.set_volume", "params": {"value": g.get("value")}}
        case "nav_start":
            return {"capability_id": "navigation.start", "params": {"destination": g.get("destination")}}
        case "nav_stop":
            return {"capability_id": "navigation.stop", "params": {}}
        case "nav_pause":
            return {"capability_id": "navigation.pause", "params": {}}
        case "nav_resume":
            return {"capability_id": "navigation.resume", "params": {}}
        case "nav_add_waypoint":
            return {"capability_id": "navigation.add_waypoint", "params": {"name": g.get("name")}}
        case "nav_remove_waypoint":
            return {"capability_id": "navigation.remove_waypoint", "params": {"name": g.get("name")}}
        case "nav_preference":
            return {"capability_id": "navigation.set_preference", "params": {"value": g.get("value")}}
        case "nav_home":
            return {"capability_id": "navigation.navigate_home", "params": {}}
        case "nav_company":
            return {"capability_id": "navigation.navigate_company", "params": {}}
        case "nav_set_home":
            return {"capability_id": "navigation.set_home", "params": {"place": g.get("place")}}
        case "nav_set_company":
            return {"capability_id": "navigation.set_company", "params": {"place": g.get("place")}}
        case "nav_query_eta":
            return {"capability_id": "navigation.query_eta", "params": {}}
        case "nav_query_status":
            return {"capability_id": "navigation.query_status", "params": {}}
        case "nav_query_waypoints":
            return {"capability_id": "navigation.query_waypoints", "params": {}}
        case "nav_prompt_enabled":
            return {"capability_id": "navigation.set_prompt_enabled", "params": {"value": g.get("value")}}
        case "nav_volume":
            return {"capability_id": "navigation.set_volume", "params": {"value": g.get("value")}}
        case "nav_muted":
            return {"capability_id": "navigation.set_muted", "params": {"value": g.get("value")}}
        case "life_search_shops":
            return {"capability_id": "life.search_shops", "params": {"keyword": g.get("keyword")}}
        case "life_enter_shop":
            return {"capability_id": "life.enter_shop", "params": {"shop_name": g.get("shop_name")}}
        case "life_add_to_cart":
            return {"capability_id": "life.add_to_cart", "params": {"item": g.get("item")}}
        case "life_go_to_checkout":
            return {"capability_id": "life.go_to_checkout", "params": {}}
        case "life_close":
            return {"capability_id": "life.close", "params": {}}
        case "light_power":
            return {"capability_id": "iot.light.set_power", "params": {"value": g.get("value")}}
        case _:
            return None


class TaskBinder:
    params = staticmethod(action_params)
    action_for = staticmethod(action_for)

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self._registry = registry if registry is not None else CapabilityRegistry()

    def bind(
        self,
        run_id: str,
        text: str,
        defaults: str,
        candidate: CompiledTaskCandidate,
    ) -> DeviceTask:
        t = DeviceTask(
            run_id=run_id,
            raw_text=text,
            defaults_rule_id=defaults,
            goals=list(candidate.goals),
            constraints=list(candidate.constraints),
        )
        for g in t.goals:
            action = action_for(g)
            if action is None:
                # Observation-only goals (no write) — skip product predicates
                if g.get("type") == "nav_diagnostic" or g.get("type") == "media_keep_muted":
                    continue
                raise ValueError(f"未注册目标类型: {java_str(g.get('type'))}")
            cap = self._registry.canonical(java_str(action.get("capability_id")))
            p = action_params(action)
            v = self._registry.validate(cap, p)
            if not v.ok:
                raise ValueError(v.message)
            exp = expected(cap, p)
            if not exp:
                src = java_str(g.get("source", "user"))
                match cap:
                    case "navigation.add_waypoint":
                        self._add(t, "nav_waypoint_contains", {"name": p.get("name")}, src)
                    case "navigation.remove_waypoint":
                        self._add(t, "nav_waypoint_absent", {"name": p.get("name")}, src)
                    case "navigation.query_eta":
                        self._add(t, "nav_query_type", {"type": "eta"}, src)
                    case "navigation.query_status":
                        self._add(t, "nav_query_type", {"type": "status"}, src)
                    case "navigation.query_waypoints":
                        self._add(t, "nav_query_type", {"type": "waypoints"}, src)
                    case _:
                        raise ValueError(f"无法为能力生成验收条件: {cap}")
            else:
                for field, value in exp.items():
                    self._add(
                        t,
                        "field_eq",
                        {"field": field, "value": value},
                        java_str(g.get("source", "user")),
                    )
            # 途经不丢终点：追加途经时额外验收终点仍在
            if cap == "navigation.add_waypoint" and g.get("retain_destination") is not None:
                self._add(
                    t,
                    "field_eq",
                    {"field": "navigation_destination", "value": g.get("retain_destination")},
                    "user",
                )
        for c in t.constraints:
            if c.get("type") == "keep_navigation_prompt":
                self._add(t, "nav_prompt_retained", {"min_volume": c.get("min_volume", 1)}, "user")
        # Audio diagnostic has a fixed product predicate, never a model-defined expression.
        if any(c.get("template_id") == "nav_prompt_event_played" for c in candidate.criteria):
            self._add(t, "nav_prompt_event_played", {}, "diagnostic contract")
        if not t.criteria:
            raise ValueError("没有可验收目标，需澄清")
        t.binding_context["summary"] = candidate.summary
        return t

    def _add(self, t: DeviceTask, template: str, p: dict[str, Any], source: str) -> None:
        t.criteria.append(
            Criterion(
                criterion_id=f"c{len(t.criteria) + 1}",
                template_id=template,
                params=p,
                required=True,
                source_ref=source,
                bound_at=utcnow(),
                bound_goal_version=t.goal_version,
            )
        )
