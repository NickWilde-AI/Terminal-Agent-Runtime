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
    def coerce_compile_node(cls, node: dict[str, Any], user_text: str | None = None) -> dict[str, Any]:
        """Repair common live-model shape drift before Pydantic construction.

        Not a Fake degrade: still uses the model's route/summary/actions when present,
        only coerces string goals / alternate action keys into the Runtime contract.
        """
        out = dict(node)
        fast = out.get("fastAction") or out.get("fast_action")
        if isinstance(fast, dict):
            out["fastAction"] = cls.normalize_action(fast)

        goals_in = out.get("goals") or []
        goals: list[dict[str, Any]] = []
        if isinstance(goals_in, dict):
            goals_in = [goals_in]
        for item in goals_in:
            if isinstance(item, dict):
                goals.append(cls.normalize_goal(item))
            elif isinstance(item, str):
                coerced = cls._goal_from_utterance(item, out.get("fastAction"))
                if coerced:
                    goals.append(coerced)
        if not goals and isinstance(out.get("fastAction"), dict):
            from_action = cls._goal_from_fast_action(out["fastAction"])
            if from_action:
                goals.append(from_action)
        if not goals and user_text:
            # Last-resort structure from the same deterministic compiler Fake uses for coverage,
            # while keeping the model's routeHint when present.
            from terminal_agent.runtime.goal_compiler import GoalCompiler

            fallback = GoalCompiler.compile(user_text, None, [])
            goals = list(fallback.goals)
            out.setdefault("constraints", fallback.constraints)
            if not out.get("fastAction") and fallback.fast_action:
                out["fastAction"] = fallback.fast_action
            out.setdefault("_coerced_from", "goal_compiler_empty_goals")
        out["goals"] = goals

        constraints = out.get("constraints") or []
        if isinstance(constraints, dict):
            constraints = [constraints]
        out["constraints"] = [c for c in constraints if isinstance(c, dict)]

        criteria = out.get("criteria") or []
        if isinstance(criteria, dict):
            criteria = [criteria]
        out["criteria"] = [c for c in criteria if isinstance(c, dict)]
        return out

    @classmethod
    def _goal_from_utterance(cls, text: str, fast_action: dict[str, Any] | None) -> dict[str, Any] | None:
        raw = text.strip()
        if not raw:
            return None
        destination = None
        if isinstance(fast_action, dict):
            params = fast_action.get("params") or {}
            destination = params.get("destination") or params.get("name")
        for prefix in ("导航到", "导航去", "去"):
            if raw.startswith(prefix):
                destination = destination or raw[len(prefix):].strip()
                break
        if destination or any(x in raw for x in ("导航", "回家", "公司")):
            goal: dict[str, Any] = {"type": "nav_start", "source": "model"}
            if destination:
                goal["value"] = destination
                goal["destination"] = destination
            return goal
        if any(x in raw for x in ("温度", "空调", "度")):
            return {"type": "cabin_temperature", "value": raw, "source": "model"}
        return {"type": "raw_utterance", "value": raw, "source": "model"}

    @classmethod
    def _goal_from_fast_action(cls, action: dict[str, Any]) -> dict[str, Any] | None:
        cap = str(action.get("capability_id") or "")
        params = dict(action.get("params") or {})
        if cap.startswith("navigation.") and (
            "start" in cap or "navigate_home" in cap or "navigate_company" in cap
        ):
            dest = params.get("destination") or params.get("name")
            goal: dict[str, Any] = {"type": "nav_start", "source": "model"}
            if dest:
                goal["value"] = dest
                goal["destination"] = dest
            if "home" in cap:
                goal["type"] = "nav_home"
            if "company" in cap:
                goal["type"] = "nav_company"
            return goal
        if "temperature" in cap:
            return {"type": "cabin_temperature", "value": params.get("value"), "source": "model"}
        return None

    KNOWN_CONSTRAINTS = {
        "no_window",
        "no_reboot",
        "no_cabin_write",
        "no_media_write",
        "keep_navigation_prompt",
    }

    @classmethod
    def normalize(cls, candidate: CompiledTaskCandidate, user_text: str | None = None) -> None:
        candidate.goals = [cls.normalize_goal(g) for g in (candidate.goals or [])]
        if candidate.fast_action is not None:
            candidate.fast_action = cls.normalize_action(candidate.fast_action)
            # Preference often only appears in the utterance; fill enum from text.
            if (
                str(candidate.fast_action.get("capability_id")) == "navigation.set_preference"
                and not (candidate.fast_action.get("params") or {}).get("value")
                and user_text
            ):
                from terminal_agent.runtime.goal_compiler import extract_preference

                mapped = extract_preference(user_text)
                if mapped:
                    candidate.fast_action["params"] = {"value": mapped}
        cleaned: list[dict[str, Any]] = []
        for item in candidate.constraints or []:
            if not isinstance(item, dict):
                continue
            type_ = str(item.get("type") or "")
            if type_ == "navigation_prompt_enabled":
                type_ = "keep_navigation_prompt"
                item = {**item, "type": type_}
            if type_ not in cls.KNOWN_CONSTRAINTS:
                continue
            if type_ == "keep_navigation_prompt" and not (
                user_text and any(x in user_text for x in ("保留导航", "导航提示", "保留提示"))
            ):
                continue
            cleaned.append(item)
        candidate.constraints = cleaned
        if candidate.criteria:
            candidate.criteria = [cls.normalize_criterion(c) for c in candidate.criteria]
        else:
            candidate.criteria = [c for g in candidate.goals if (c := cls.criterion_from_goal(g))]
        cls.correct_route(candidate, user_text)

    @classmethod
    def normalize_action(cls, action: dict[str, Any]) -> dict[str, Any]:
        out = dict(action)
        raw = str(
            out.get("capability_id")
            or out.get("capabilityId")
            or out.get("action")
            or out.get("name")
            or ""
        )
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
        # Live models often attach preference onto start; schema is exact-key match.
        if capability == "navigation.start":
            dest = params.get("destination")
            if dest is None:
                dest = params.get("value") or params.get("name")
            params = {"destination": dest} if dest is not None else {}
        elif capability in ("navigation.add_waypoint", "navigation.remove_waypoint"):
            name = params.get("name")
            if name is None:
                name = params.get("value") or params.get("destination")
            params = {"name": name} if name is not None else {}
        elif capability == "navigation.set_preference":
            from terminal_agent.runtime.goal_compiler import extract_preference

            raw_value = params.get("value")
            mapped = None
            if isinstance(raw_value, str):
                if raw_value in {
                    "fastest",
                    "shortest",
                    "avoid_highway",
                    "avoid_congestion",
                    "less_toll",
                    "less_detour",
                }:
                    mapped = raw_value
                else:
                    mapped = extract_preference(raw_value)
            params = {"value": mapped} if mapped is not None else {}
        elif capability in ("navigation.navigate_home", "navigation.navigate_company"):
            params = {}
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
        if out.get("type") == "nav_start" and out.get("destination") is None and out.get("value") is not None:
            out["destination"] = out["value"]
        if out.get("type") in ("nav_add_waypoint", "nav_remove_waypoint") and out.get("name") is None:
            out["name"] = out.get("value") or out.get("destination")
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
        goal_types = {str(g.get("type")) for g in candidate.goals or []}
        simple_nav = {
            "nav_home",
            "nav_company",
            "nav_preference",
            "nav_query_eta",
            "nav_query_status",
            "nav_query_waypoints",
            "nav_stop",
            "nav_pause",
            "nav_resume",
        }
        if goal_types and goal_types <= simple_nav and not candidate.constraints and not cls.looks_complex_request(
            text or ""
        ):
            candidate.route_hint = "FAST"
            if candidate.fast_action is None and len(candidate.goals) == 1:
                from terminal_agent.runtime.task_binder import TaskBinder

                action = TaskBinder.action_for(candidate.goals[0])
                if action:
                    candidate.fast_action = cls.normalize_action(action)
            candidate.raw["route_corrected"] = "simple_nav_force_fast"
            return
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
