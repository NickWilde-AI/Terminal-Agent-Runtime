"""Evidence-based verifier: the sole authority allowed to complete a run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from terminal_agent.capability.core import eq
from terminal_agent.contracts import (
    Attribution,
    Criterion,
    ExecutionStatus,
    GoalOutcome,
    RunRecord,
    StateSnapshot,
    VerificationStatus,
    now,
)
from terminal_agent.device.port import DevicePort


@dataclass
class VerificationResult:
    outcome: GoalOutcome
    summary: str
    details: list[dict[str, Any]]
    snapshot: StateSnapshot


class Verifier:
    def __init__(self, device: DevicePort) -> None:
        self.device = device

    async def verify_task(self, run: RunRecord) -> VerificationResult:
        try:
            run.budget.count_tool()
            snapshot = await self.device.read_state(None)
        except Exception:
            snapshot = await self.device.snapshot()
            return VerificationResult(
                GoalOutcome.UNKNOWN,
                "验证不可用，不能确认目标已满足",
                [{"status": "UNKNOWN", "detail": "读取不可用"}],
                snapshot,
            )
        fresh = (
            snapshot.observed_at is not None
            and snapshot.observed_at > now() - timedelta(seconds=2)
            and snapshot.environment_id == run.environment_id
        )
        details = [
            {
                "criterion_id": criterion.criterion_id,
                "template_id": criterion.template_id,
                "params": criterion.params,
                "status": "UNKNOWN"
                if not fresh
                else "SATISFIED"
                if self.check(criterion, snapshot)
                else "NOT_SATISFIED",
            }
            for criterion in run.task.criteria
        ]
        unresolved = run.unresolved_unknown or any(a.execution_status == ExecutionStatus.UNKNOWN for a in run.actions)
        if unresolved or not fresh:
            outcome = GoalOutcome.UNKNOWN
        elif details and all(d["status"] == "SATISFIED" for d in details):
            outcome = GoalOutcome.SATISFIED
        else:
            outcome = GoalOutcome.UNSATISFIED
        summary = (
            "结果未知，保留已知动作事实，停止新写"
            if outcome == GoalOutcome.UNKNOWN
            else "仍有目标未满足，请查看逐项证据"
            if outcome == GoalOutcome.UNSATISFIED
            else self._summary(run, snapshot)
        )
        return VerificationResult(outcome, summary, details, snapshot)

    @staticmethod
    def check(criterion: Criterion, snapshot: StateSnapshot) -> bool:
        state, params, template = snapshot.state, criterion.params, criterion.template_id
        if template == "field_eq":
            return eq(state.get(str(params.get("field"))), params.get("value"))
        if template == "cabin_temperature_eq":
            return eq(state.get("temperature_setpoint"), params.get("value"))
        if template == "cabin_fan_eq":
            return eq(state.get("fan_level"), params.get("value"))
        if template == "media_volume_eq":
            return eq(state.get("media_volume"), params.get("value"))
        if template == "nav_prompt_retained":
            return bool(
                state.get("navigation_active")
                and state.get("prompt_enabled")
                and not state.get("navigation_muted")
                and state.get("route_available")
                and state.get("focus_available")
                and state.get("navigation_volume", 0) >= params.get("min_volume", 1)
            )
        if template == "nav_prompt_event_played":
            from datetime import datetime

            at = state.get("last_prompt_at")
            observed = datetime.fromisoformat(str(at).replace("Z", "+00:00")) if at else None
            return bool(
                state.get("last_prompt_result") == "PLAYED"
                and observed
                and criterion.bound_at
                and observed > criterion.bound_at
                and eq(state.get("last_prompt_navigation_revision"), snapshot.domain_revisions.get("NAVIGATION"))
            )
        if template == "nav_waypoint_contains":
            return params.get("name") in state.get("navigation_waypoints", [])
        if template == "nav_waypoint_absent":
            return params.get("name") not in state.get("navigation_waypoints", [])
        if template == "nav_query_type":
            return state.get("last_nav_query_type") == params.get("type")
        if template == "light_power_eq":
            return eq(state.get("light_power"), params.get("value"))
        return False

    @staticmethod
    def _summary(run: RunRecord, snapshot: StateSnapshot) -> str:
        state = snapshot.state
        verified = sum(
            a.execution_status == ExecutionStatus.APPLIED
            and a.attribution == Attribution.THIS_ACTION
            and a.verification_status == VerificationStatus.SATISFIED
            for a in run.actions
        )
        text = (
            f"当前目标已满足；{verified} 项动作有应用与回读证据。" if verified else "当前设定已是目标值，无需重复写入。"
        )
        text += f" 空调电源 {'开' if state.get('climate_power') else '关'}，设定 {state.get('temperature_setpoint')}℃"
        text += f"，舱温 {state.get('cabin_temperature')}℃（设定温度≠当前舱温）。车窗 左前/右前/左后/右后 "
        text += "/".join(
            str(state.get(f"window_{x}")) for x in ("front_left", "front_right", "rear_left", "rear_right")
        )
        text += "。媒体播放中（占位曲目，无真实音频）" if state.get("media_playing") else "。媒体未播放"
        if state.get("navigation_active"):
            text += f"。导航进行中 → {state.get('navigation_destination', '—')}"
            if state.get("navigation_waypoints"):
                text += f"，途经 {state['navigation_waypoints']}"
            if state.get("navigation_paused"):
                text += "（已暂停）"
            if state.get("navigation_eta_minutes") is not None:
                text += f"，ETA {state['navigation_eta_minutes']} 分钟"
            text += "（播报开关开启≠用户已听到声音）"
        if state.get("last_nav_query_result"):
            text += f"。最近查询：{state['last_nav_query_result']}"
        return text + "。以上为本地模拟器状态，不代表真实设备。"
