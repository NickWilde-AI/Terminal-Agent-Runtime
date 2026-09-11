"""Only the product contract creates required predicates; model criteria cannot weaken them."""

from __future__ import annotations

from typing import Any

from terminal_agent.capability.core import CapabilityRegistry, expected_effects
from terminal_agent.contracts import CompiledTaskCandidate, Criterion, DeviceTask, now


def java_str(value: Any) -> str:
    """Mirror Java String.valueOf so null-derived branches stay behaviourally identical."""
    return "null" if value is None else str(value)


def action_params(action: dict[str, Any]) -> dict[str, Any]:
    params = action.get("params")
    return dict(params) if isinstance(params, dict) else {}


def action_for(goal: dict[str, Any]) -> dict[str, Any] | None:
    if "capability_id" in goal:
        return {"capability_id": goal.get("capability_id"), "params": goal.get("params", {})}
    type_ = java_str(goal.get("type"))
    match type_:
        case "climate_power":
            return {"capability_id": "climate.set_power", "params": {"value": goal.get("value")}}
        case "cabin_temperature":
            return {"capability_id": "climate.set_temperature", "params": {"value": goal.get("value")}}
        case "cabin_fan":
            return {"capability_id": "climate.set_fan", "params": {"value": goal.get("value")}}
        case "window_position":
            return {
                "capability_id": "window.set_position",
                "params": {"window": goal.get("window", "all"), "position": goal.get("position")},
            }
        case "media_play":
            return {"capability_id": "media.play", "params": {"artist": goal.get("artist")}}
        case "media_pause":
            return {"capability_id": "media.pause", "params": {}}
        case "media_volume":
            return {"capability_id": "media.set_volume", "params": {"value": goal.get("value")}}
        case "nav_start":
            dest = goal.get("destination")
            if dest is None:
                dest = goal.get("value")
            return {"capability_id": "navigation.start", "params": {"destination": dest}}
        case "nav_stop":
            return {"capability_id": "navigation.stop", "params": {}}
        case "nav_pause":
            return {"capability_id": "navigation.pause", "params": {}}
        case "nav_resume":
            return {"capability_id": "navigation.resume", "params": {}}
        case "nav_add_waypoint":
            name = goal.get("name")
            if name is None:
                name = goal.get("value")
            return {"capability_id": "navigation.add_waypoint", "params": {"name": name}}
        case "nav_remove_waypoint":
            name = goal.get("name")
            if name is None:
                name = goal.get("value")
            return {"capability_id": "navigation.remove_waypoint", "params": {"name": name}}
        case "nav_preference":
            return {"capability_id": "navigation.set_preference", "params": {"value": goal.get("value")}}
        case "nav_home":
            return {"capability_id": "navigation.navigate_home", "params": {}}
        case "nav_company":
            return {"capability_id": "navigation.navigate_company", "params": {}}
        case "nav_set_home":
            return {"capability_id": "navigation.set_home", "params": {"place": goal.get("place")}}
        case "nav_set_company":
            return {"capability_id": "navigation.set_company", "params": {"place": goal.get("place")}}
        case "nav_query_eta":
            return {"capability_id": "navigation.query_eta", "params": {}}
        case "nav_query_status":
            return {"capability_id": "navigation.query_status", "params": {}}
        case "nav_query_waypoints":
            return {"capability_id": "navigation.query_waypoints", "params": {}}
        case "nav_prompt_enabled":
            return {"capability_id": "navigation.set_prompt_enabled", "params": {"value": goal.get("value")}}
        case "nav_volume":
            return {"capability_id": "navigation.set_volume", "params": {"value": goal.get("value")}}
        case "nav_muted":
            return {"capability_id": "navigation.set_muted", "params": {"value": goal.get("value")}}
        case "life_search_shops":
            return {"capability_id": "life.search_shops", "params": {"keyword": goal.get("keyword")}}
        case "life_enter_shop":
            return {"capability_id": "life.enter_shop", "params": {"shop_name": goal.get("shop_name")}}
        case "life_add_to_cart":
            return {"capability_id": "life.add_to_cart", "params": {"item": goal.get("item")}}
        case "life_go_to_checkout":
            return {"capability_id": "life.go_to_checkout", "params": {}}
        case "life_close":
            return {"capability_id": "life.close", "params": {}}
        case "light_power":
            return {"capability_id": "iot.light.set_power", "params": {"value": goal.get("value")}}
        case _:
            return None


class TaskBinder:
    """Single product binder used by harness, baseline, fake, and OpenAI paths."""

    params = staticmethod(action_params)
    action_for = staticmethod(action_for)

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self.registry = registry if registry is not None else CapabilityRegistry()

    def bind(self, run_id: str, text: str, defaults: str, candidate: CompiledTaskCandidate) -> DeviceTask:
        task = DeviceTask(
            run_id=run_id,
            raw_text=text,
            defaults_rule_id=defaults,
            goals=list(candidate.goals),
            constraints=list(candidate.constraints),
        )
        for goal in task.goals:
            action = action_for(goal)
            if action is None:
                if goal.get("type") in ("nav_diagnostic", "media_keep_muted"):
                    continue
                raise ValueError(f"未注册目标类型: {java_str(goal.get('type'))}")
            cap = self.registry.canonical(java_str(action.get("capability_id")))
            params = action_params(action)
            validation = self.registry.validate(cap, params)
            if not validation.ok:
                raise ValueError(validation.message)
            expected = expected_effects(cap, params)
            if expected:
                for field, value in expected.items():
                    self._add(task, "field_eq", {"field": field, "value": value}, java_str(goal.get("source", "user")))
            else:
                special_map: dict[str, tuple[str, dict[str, Any]]] = {
                    "navigation.add_waypoint": ("nav_waypoint_contains", {"name": params.get("name")}),
                    "navigation.remove_waypoint": ("nav_waypoint_absent", {"name": params.get("name")}),
                    "navigation.query_eta": ("nav_query_type", {"type": "eta"}),
                    "navigation.query_status": ("nav_query_type", {"type": "status"}),
                    "navigation.query_waypoints": ("nav_query_type", {"type": "waypoints"}),
                }
                special = special_map.get(cap)
                if not special:
                    raise ValueError(f"无法为能力生成验收条件: {cap}")
                template_id, criterion_params = special
                self._add(
                    task,
                    template_id,
                    criterion_params,
                    java_str(goal.get("source", "user")),
                )
            if cap == "navigation.add_waypoint" and goal.get("retain_destination") is not None:
                self._add(
                    task,
                    "field_eq",
                    {"field": "navigation_destination", "value": goal.get("retain_destination")},
                    "user",
                )
        for constraint in task.constraints:
            if constraint.get("type") == "keep_navigation_prompt":
                self._add(task, "nav_prompt_retained", {"min_volume": constraint.get("min_volume", 1)}, "user")
        if any(c.get("template_id") == "nav_prompt_event_played" for c in candidate.criteria):
            self._add(task, "nav_prompt_event_played", {}, "diagnostic contract")
        if not task.criteria:
            raise ValueError("没有可验收目标，需澄清")
        task.binding_context["summary"] = candidate.summary
        return task

    @staticmethod
    def _add(task: DeviceTask, template: str, params: dict[str, Any], source: str) -> None:
        task.criteria.append(
            Criterion(
                criterion_id=f"c{len(task.criteria) + 1}",
                template_id=template,
                params=params,
                required=True,
                source_ref=source,
                bound_at=now(),
                bound_goal_version=task.goal_version,
            )
        )
