"""Normalize model output into the runtime's canonical wire contract."""

from __future__ import annotations

from typing import Any

from terminal_agent.agent.contracts import CompiledTaskCandidate


class ModelOutputNormalizer:
    GOAL_ALIASES = {
        "temperature": "cabin_temperature", "temp": "cabin_temperature",
        "cabin_temp": "cabin_temperature", "ac_temperature": "cabin_temperature",
        "fan": "cabin_fan", "fan_level": "cabin_fan",
        "power": "climate_power", "ac_power": "climate_power", "climate_on": "climate_power",
        "volume": "media_volume", "media": "media_volume", "media_vol": "media_volume",
        "play": "media_play", "play_media": "media_play", "pause": "media_pause",
        "window": "window_position", "window_open": "window_position", "window_pos": "window_position",
        "navigate": "nav_start", "navigation_start": "nav_start", "nav_destination": "nav_start",
        "nav_prompt": "nav_prompt_enabled", "prompt_enabled": "nav_prompt_enabled",
        "nav_mute": "nav_muted", "navigation_muted": "nav_muted",
        "nav_vol": "nav_volume", "navigation_volume": "nav_volume",
    }
    CRITERIA = {
        "cabin_temperature": "cabin_temperature_eq", "cabin_fan": "cabin_fan_eq",
        "media_volume": "media_volume_eq", "nav_prompt_enabled": "nav_prompt_enabled_eq",
        "nav_muted": "nav_muted_eq", "nav_volume": "nav_volume_eq",
    }

    @classmethod
    def normalize(cls, candidate: CompiledTaskCandidate, user_text: str | None = None) -> None:
        candidate.goals = [cls.normalize_goal(g) for g in (candidate.goals or [])]
        if candidate.fast_action is not None:
            candidate.fast_action = cls.normalize_action(candidate.fast_action)
        candidate.constraints = candidate.constraints or []
        if candidate.criteria:
            candidate.criteria = [cls.normalize_criterion(c) for c in candidate.criteria]
        else:
            candidate.criteria = [c for g in candidate.goals if (c := cls.criterion_from_goal(g))]
        cls.correct_route(candidate, user_text)

    @classmethod
    def normalize_action(cls, action: dict[str, Any]) -> dict[str, Any]:
        out = dict(action)
        raw = str(out.get("capability_id", out.get("capabilityId", "")))
        if "." in raw:
            capability = raw
        else:
            prefixes = {
                "climate_": "climate.", "cabin_": "climate.", "media_": "media.",
                "navigation_": "navigation.", "window_": "window.", "device_": "device.",
            }
            capability = raw.replace("_", ".")
            for prefix, replacement in prefixes.items():
                if raw.startswith(prefix):
                    capability = replacement + raw[len(prefix):]
                    break
        out["capability_id"] = capability
        params = dict(out.get("params") or {})
        exempt = capability.endswith((".play", ".pause", ".start", ".stop")) or "window" in capability
        if "value" not in params and not exempt:
            for alias in ("temperature", "temp", "fan", "fan_level", "volume", "enabled", "muted", "power"):
                if alias in params:
                    params["value"] = params[alias]
                    break
        if "window" in capability and "position" in params and "window" not in params:
            params["window"] = params.get("id", "all")
        out["params"] = params
        out.setdefault("decision", "ACT")
        return out

    @classmethod
    def normalize_goal(cls, goal: dict[str, Any]) -> dict[str, Any]:
        out = dict(goal)
        out["type"] = cls.GOAL_ALIASES.get(str(out.get("type", "")), str(out.get("type", "")))
        if "value" not in out:
            for alias in ("temperature", "temp", "fan", "volume", "enabled", "muted", "power"):
                if alias in out:
                    out["value"] = out[alias]
                    break
        return out

    @staticmethod
    def normalize_criterion(raw: dict[str, Any]) -> dict[str, Any]:
        out = dict(raw)
        if "template_id" not in out and "templateId" in out:
            out["template_id"] = out["templateId"]
        params = dict(out.get("params") or {})
        if "value" not in params:
            for alias in ("temperature", "temp", "fan", "volume", "enabled", "muted"):
                if alias in params:
                    params["value"] = params[alias]
                    break
        out["params"] = params
        return out

    @classmethod
    def criterion_from_goal(cls, goal: dict[str, Any]) -> dict[str, Any] | None:
        template = cls.CRITERIA.get(str(goal.get("type")))
        if not template:
            return None
        return {"template_id": template, "params": {"value": goal.get("value")},
                "required": True, "source": str(goal.get("source", "model"))}

    @classmethod
    def correct_route(cls, candidate: CompiledTaskCandidate, text: str | None) -> None:
        if (candidate.route_hint or "").upper() != "FAST":
            return
        reason = None
        if cls.looks_complex_request(text or ""):
            reason = "complex_request_force_multi_agent"
        elif len(candidate.goals) > 1:
            reason = "multi_goal_force_multi_agent"
        elif candidate.constraints:
            reason = "constraints_force_multi_agent"
        elif cls._multi_domain(candidate.goals):
            reason = "multi_domain_force_multi_agent"
        if reason:
            candidate.route_hint = "MULTI_AGENT"
            candidate.raw["route_corrected"] = reason

    @staticmethod
    def looks_complex_request(text: str) -> bool:
        if not text:
            return False
        if any(x in text for x in ("休息", "舒服", "不要开窗", "不开窗", "保留导航", "导航提示",
                                   "不要重启", "不重启", "不调空调", "空调先不要")):
            return True
        if "导航" in text and any(x in text for x in ("没有声音", "无声", "听不见")):
            return True
        hits = sum(any(k in text for k in group) for group in
                   (("温度", "空调"), ("风量",), ("车窗", "开窗"), ("媒体", "音量", "播放"), ("导航",)))
        return (any(x in text for x in ("并且", "同时", "再", "还要", "然后", "；")) and hits >= 2) or hits >= 3

    @staticmethod
    def _multi_domain(goals: list[dict[str, Any]]) -> bool:
        domains = set()
        for goal in goals:
            kind = str(goal.get("type", ""))
            if kind.startswith("cabin_") or kind == "climate_power":
                domains.add("cabin")
            elif kind.startswith("media_"):
                domains.add("media")
            elif kind.startswith("nav_"):
                domains.add("navigation")
            elif kind == "window_position":
                domains.add("window")
        return len(domains) >= 2
