"""Acceptance-agent helpers: stamp deterministic facts onto LLM-writable audit fields."""

from __future__ import annotations

from typing import Any

from terminal_agent.contracts import (
    AuditResult,
    ExecutionStatus,
    GoalResult,
    GoalResultStatus,
    OverallOutcome,
    RunRecord,
    ToolAction,
)


def execution_evidence(run: RunRecord) -> list[dict[str, Any]]:
    return [
        {
            "action_id": action.action_id,
            "capability_id": action.capability_id,
            "params": action.params,
            "execution_status": action.execution_status.value,
            "verification_status": action.verification_status.value if action.verification_status else None,
            "attribution": action.attribution.value,
            "observed_at": action.finished_at,
            "goal_version": action.goal_version,
            "message": action.message,
        }
        for action in run.actions
    ]


def stamp_audit(
    draft: AuditResult,
    goal_results: list[GoalResult],
    overall_outcome: OverallOutcome,
    run_id: str | None = None,
    goal_version: int = 0,
    model_id: str | None = None,
) -> AuditResult:
    """Copy only auditor-writable fields; overwrite both deterministic result layers."""
    stamped = AuditResult(
        evidence_gaps=list(draft.evidence_gaps or []),
        explanation=draft.explanation or "",
        replan_required=bool(draft.replan_required),
        replan_reason=draft.replan_reason,
        final_reply_draft=draft.final_reply_draft,
        goal_results=[item.model_copy(deep=True) for item in goal_results],
        overall_outcome=overall_outcome,
        run_id=run_id or draft.run_id,
        goal_version=goal_version or draft.goal_version,
        model_id=model_id or draft.model_id,
        raw=dict(draft.raw or {}),
    )
    if overall_outcome in {OverallOutcome.COMPLETED, OverallOutcome.UNKNOWN}:
        stamped.replan_required = False
        if overall_outcome == OverallOutcome.UNKNOWN:
            stamped.replan_reason = stamped.replan_reason or "UNKNOWN 不能当失败重规划"
    stamped.raw["stamped"] = True
    return stamped


def deterministic_audit(
    goal_results: list[GoalResult],
    overall_outcome: OverallOutcome,
    run: RunRecord | None = None,
) -> AuditResult:
    unsatisfied = [item for item in goal_results if item.required and item.status == GoalResultStatus.UNSATISFIED]
    unknown = [
        item
        for item in goal_results
        if item.required and item.status in {GoalResultStatus.UNKNOWN, GoalResultStatus.PENDING}
    ]
    gaps = [f"{item.template_id}:{item.status.value}" for item in unsatisfied + unknown]
    if overall_outcome == OverallOutcome.COMPLETED:
        explanation = "全部必需目标已满足。"
        reply = (run.result_summary if run else None) or explanation
        return AuditResult(
            explanation=explanation,
            final_reply_draft=reply,
            replan_required=False,
            evidence_gaps=[],
        )
    if overall_outcome == OverallOutcome.UNKNOWN:
        explanation = "存在未知或等待中的必需目标，不能当作失败或成功。"
        return AuditResult(
            explanation=explanation,
            final_reply_draft=explanation,
            replan_required=False,
            evidence_gaps=gaps,
            replan_reason="UNKNOWN 不重规划",
        )
    explanation = "仍有必需目标未满足，建议重规划未完成部分。"
    return AuditResult(
        explanation=explanation,
        final_reply_draft=explanation,
        replan_required=True,
        replan_reason="required goals unsatisfied",
        evidence_gaps=gaps,
    )


def should_replan(run: RunRecord, audit: AuditResult) -> bool:
    if not audit.replan_required:
        return False
    if audit.overall_outcome in {OverallOutcome.COMPLETED, OverallOutcome.UNKNOWN, None}:
        return False
    if run.is_terminal() or run.cancel_accepted or run.budget.expired():
        return False
    try:
        run.budget.count_replan()
    except RuntimeError:
        return False
    return True


def unknown_write(run: RunRecord) -> ToolAction | None:
    return next((action for action in run.actions if action.execution_status == ExecutionStatus.UNKNOWN), None)
