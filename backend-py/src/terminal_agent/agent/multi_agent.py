"""Deterministic helpers shared by Fake planner/reviewer and harness wiring."""

from __future__ import annotations

from typing import Any

from terminal_agent.agent.contracts import (
    DeviceTask,
    PlanDraft,
    ReviewDecision,
    ReviewResult,
    StateSnapshot,
    TaskSpec,
)
from terminal_agent.model.normalizer import ModelOutputNormalizer
from terminal_agent.runtime.task_binder import action_for, java_str


def task_spec_from(task: DeviceTask, run_id: str | None, model_id: str | None) -> TaskSpec:
    spec = TaskSpec()
    spec.run_id = run_id
    spec.model_id = model_id
    spec.goal_version = task.goal_version
    spec.goal = java_str(task.binding_context.get("summary", task.raw_text))
    spec.goals = list(task.goals)
    spec.constraints = list(task.constraints)
    for c in task.criteria:
        spec.success_criteria.append({"template_id": c.template_id, "params": c.params, "required": c.required})
    for g in task.goals:
        action = action_for(g)
        if action is not None:
            spec.allowed_capabilities.append(java_str(action.get("capability_id")))
    spec.allowed_capabilities = list(dict.fromkeys(spec.allowed_capabilities))
    return spec


def _int_of(value: Any) -> int:
    """Mirror Java's ((Number) x).intValue(): raises when the goal field is absent."""
    return int(value)


def _alias_match(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    if a == b:
        return True
    return a.replace("cabin.", "climate.") == b.replace("cabin.", "climate.")


def _goal_covers_capability(goals: list[dict[str, Any]] | None, cap: str) -> bool:
    if goals is None:
        return False
    for g in goals:
        action = action_for(g)
        if action is not None and _alias_match(java_str(action.get("capability_id")), cap):
            return True
    return False


def build_plan_draft(
    spec: TaskSpec,
    observation: StateSnapshot | None,
    prior_actions: list[dict[str, Any]] | None,
    revision_round: int,
    model_id: str | None,
) -> PlanDraft:
    """Build a full candidate plan covering unmet goals (Fake / baseline planner).

    Does not execute — only proposes actions.
    """
    draft = PlanDraft()
    draft.run_id = spec.run_id
    draft.goal_version = spec.goal_version
    draft.model_id = model_id
    draft.revision_round = revision_round
    state: dict[str, Any] = {} if observation is None else observation.state
    no_cabin = _has_constraint(spec.constraints, "no_cabin_write")
    no_window = _has_constraint(spec.constraints, "no_window")
    no_media = _has_constraint(spec.constraints, "no_media_write")

    idx = 0
    for goal in spec.goals:
        type_ = java_str(goal.get("type"))
        action: dict[str, Any] | None = None
        if type_ == "climate_power" and not no_cabin:
            target = goal.get("value") is True
            if (state.get("climate_power") is True) != target:
                action = _act("climate.set_power", {"value": target}, "空调电源")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "cabin_temperature" and not no_cabin:
            target_i = _int_of(goal.get("value"))
            cur = int(state.get("temperature_setpoint", 26))
            if cur != target_i:
                action = _act("climate.set_temperature", {"value": target_i}, "温度")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "cabin_fan" and not no_cabin:
            target_i = _int_of(goal.get("value"))
            cur = int(state.get("fan_level", 3))
            if cur != target_i:
                action = _act("climate.set_fan", {"value": target_i}, "风量")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "window_position" and not no_window:
            window = java_str(goal.get("window", "all"))
            position = _int_of(goal.get("position"))
            action = _act("window.set_position", {"window": window, "position": position}, "车窗")
        elif type_ == "media_play" and not no_media:
            artist = java_str(goal.get("artist"))
            playing = state.get("media_playing") is True
            cur_s = java_str(state.get("media_artist", ""))
            if not playing or artist != cur_s:
                action = _act("media.play", {"artist": artist}, "媒体播放")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "media_pause" and not no_media:
            if state.get("media_playing") is True:
                action = _act("media.pause", {}, "媒体暂停")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "media_volume" and not no_media:
            if state.get("media_muted") is not True:
                target_i = _int_of(goal.get("value"))
                cur = int(state.get("media_volume", 8))
                if cur != target_i:
                    action = _act("media.set_volume", {"value": target_i}, "媒体音量")
                else:
                    draft.assumptions.append(type_ + " already satisfied")
            else:
                draft.assumptions.append("media muted — skip volume write")
        elif type_ == "nav_start":
            dest = java_str(goal.get("destination"))
            active = state.get("navigation_active") is True
            cur_s = java_str(state.get("navigation_destination", ""))
            if not active or dest != cur_s:
                action = _act("navigation.start", {"destination": dest}, "导航启动")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_stop":
            if state.get("navigation_active") is True:
                action = _act("navigation.stop", {}, "导航停止")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_home":
            home = state.get("navigation_home")
            active = state.get("navigation_active") is True
            if not active or home != state.get("navigation_destination"):
                action = _act("navigation.navigate_home", {}, "导航回家")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_company":
            company = state.get("navigation_company")
            active = state.get("navigation_active") is True
            if not active or company != state.get("navigation_destination"):
                action = _act("navigation.navigate_company", {}, "导航去公司")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_add_waypoint":
            name = java_str(goal.get("name"))
            wp = state.get("navigation_waypoints")
            has = isinstance(wp, list) and name in wp
            if not has:
                action = _act("navigation.add_waypoint", {"name": name}, "追加途经点")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_remove_waypoint":
            name = java_str(goal.get("name"))
            wp = state.get("navigation_waypoints")
            has = isinstance(wp, list) and name in wp
            if has:
                action = _act("navigation.remove_waypoint", {"name": name}, "删除途经点")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_preference":
            pref = java_str(goal.get("value"))
            if pref != java_str(state.get("navigation_preference", "")):
                action = _act("navigation.set_preference", {"value": pref}, "路线偏好")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_pause":
            if state.get("navigation_paused") is not True:
                action = _act("navigation.pause", {}, "暂停导航")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_resume":
            if state.get("navigation_paused") is True:
                action = _act("navigation.resume", {}, "继续导航")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_query_eta":
            action = _act("navigation.query_eta", {}, "查询ETA")
        elif type_ == "nav_query_status":
            action = _act("navigation.query_status", {}, "查询导航状态")
        elif type_ == "nav_query_waypoints":
            action = _act("navigation.query_waypoints", {}, "查询途经点")
        elif type_ == "nav_prompt_enabled":
            target = goal.get("value") is True
            if (state.get("prompt_enabled") is True) != target:
                action = _act("navigation.set_prompt_enabled", {"value": target}, "导航播报")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_muted":
            target = goal.get("value") is True
            if (state.get("navigation_muted") is True) != target:
                action = _act("navigation.set_muted", {"value": target}, "导航静音")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_volume":
            target_i = _int_of(goal.get("value"))
            cur = int(state.get("navigation_volume", 5))
            if cur != target_i:
                action = _act("navigation.set_volume", {"value": target_i}, "导航音量")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "nav_diagnostic" or type_ == "media_keep_muted":
            draft.assumptions.append("观察类目标：" + type_ + "，不产生写动作")
        elif type_ == "life_search_shops":
            action = _act("life.search_shops", {"keyword": java_str(goal.get("keyword", "美食"))}, "生活服务搜店")
        elif type_ == "life_enter_shop":
            action = _act("life.enter_shop", {"shop_name": java_str(goal.get("shop_name"))}, "生活服务进店")
        elif type_ == "life_add_to_cart":
            action = _act("life.add_to_cart", {"item": java_str(goal.get("item"))}, "生活服务加购")
        elif type_ == "life_go_to_checkout":
            action = _act("life.go_to_checkout", {}, "生活服务去结算")
        elif type_ == "life_close":
            if state.get("life_session_active") is True:
                action = _act("life.close", {}, "关闭外卖会话")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        elif type_ == "light_power":
            target = goal.get("value") is True
            if (state.get("light_power") is True) != target:
                action = _act("iot.light.set_power", {"value": target}, "智能灯开关")
            else:
                draft.assumptions.append(type_ + " already satisfied")
        if action is not None:
            action = ModelOutputNormalizer.normalize_action(action)
            draft.actions.append(action)
            draft.order.append(idx)
            idx += 1
            draft.expected_effects.append(
                {"capability_id": action.get("capability_id"), "params": action.get("params")}
            )
    if not draft.actions:
        draft.assumptions.append("观察显示目标已满足或无需写动作")
    if prior_actions:
        draft.preconditions.append({"prior_actions": len(prior_actions)})
    return draft


def review(spec: TaskSpec, draft: PlanDraft, model_id: str | None) -> ReviewResult:
    """Deterministic semantic review used by Fake and as OpenAI parse fallback."""
    result = ReviewResult()
    result.run_id = spec.run_id
    result.goal_version = spec.goal_version
    result.model_id = model_id

    no_cabin = _has_constraint(spec.constraints, "no_cabin_write")
    no_window = _has_constraint(spec.constraints, "no_window")
    no_media = _has_constraint(spec.constraints, "no_media_write")

    for action in draft.actions:
        cap = java_str(action.get("capability_id"))
        if no_cabin and cap.startswith("climate."):
            result.violated_constraints.append("no_cabin_write vs " + cap)
        if no_window and cap.startswith("window."):
            result.violated_constraints.append("no_window vs " + cap)
        if no_media and cap.startswith("media."):
            result.violated_constraints.append("no_media_write vs " + cap)
        if (
            spec.allowed_capabilities
            and not any(a == cap or _alias_match(a, cap) for a in spec.allowed_capabilities)
            and cap != "device.get_state"
            and cap != "device.read_state"
            and not _goal_covers_capability(spec.goals, cap)
        ):
            result.risky_actions.append("capability not in allowed set: " + cap)

    for goal in spec.goals:
        type_ = java_str(goal.get("type"))
        if type_ == "nav_diagnostic" or type_ == "media_keep_muted":
            continue
        if type_ == "cabin_temperature" and no_cabin:
            continue
        if type_ == "cabin_fan" and no_cabin:
            continue
        if type_ == "climate_power" and no_cabin:
            continue
        if type_ == "window_position" and no_window:
            continue
        if type_.startswith("media_") and no_media:
            continue
        needed = action_for(goal)
        if needed is None:
            continue
        need_cap = java_str(needed.get("capability_id"))
        covered = any(_alias_match(need_cap, java_str(a.get("capability_id"))) for a in draft.actions)
        assumed_ok = any(
            type_ in s and ("already satisfied" in s or "不产生写动作" in s or "skip" in s) for s in draft.assumptions
        )
        all_done = not draft.actions and any(("已满足" in s or "无需写动作" in s) for s in draft.assumptions)
        if not covered and not assumed_ok and not all_done:
            result.missing_goals.append(type_ + " → " + need_cap)

    if result.violated_constraints or result.risky_actions:
        result.decision = ReviewDecision.REJECT
        result.suggestions.append("移除违规动作或收紧 allowed_capabilities 后重试")
        return result
    if result.missing_goals:
        result.decision = ReviewDecision.REVISE
        result.suggestions.append("补齐遗漏目标对应的候选动作：" + ", ".join(result.missing_goals))
        return result
    result.decision = ReviewDecision.PASS
    return result


def omit_climate_actions(draft: PlanDraft) -> PlanDraft:
    """Inject a deliberate omission for tests: drop first climate action."""
    copy = PlanDraft()
    copy.run_id = draft.run_id
    copy.goal_version = draft.goal_version
    copy.model_id = draft.model_id
    copy.revision_round = draft.revision_round
    copy.assumptions = list(draft.assumptions)
    copy.unresolved = list(draft.unresolved)
    i = 0
    for a in draft.actions:
        if java_str(a.get("capability_id")).startswith("climate."):
            continue
        copy.actions.append(a)
        copy.order.append(i)
        i += 1
    return copy


def _has_constraint(constraints: list[dict[str, Any]] | None, type_: str) -> bool:
    return constraints is not None and any(c.get("type") == type_ for c in constraints)


def _act(capability_id: str, params: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"decision": "ACT", "capability_id": capability_id, "params": params, "reason": reason}


class MultiAgentSupport:
    """Java-compatible namespace facade used by model adapters."""

    task_spec_from = staticmethod(task_spec_from)
    build_plan_draft = staticmethod(build_plan_draft)
    review = staticmethod(review)
    omit_climate_actions = staticmethod(omit_climate_actions)
