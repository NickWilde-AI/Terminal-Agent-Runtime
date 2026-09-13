"""Deterministic overall-outcome aggregation. Not an Agent; not LLM-overridable."""

from __future__ import annotations

from terminal_agent.contracts import GoalResult, GoalResultStatus, OverallOutcome


class OutcomeAggregator:
    """Compute overall_outcome from required goal_results.

    UNKNOWN / PENDING are neither success nor failure.
    SCHEDULED required goals prevent COMPLETED.
    """

    @staticmethod
    def aggregate(goal_results: list[GoalResult] | None) -> OverallOutcome:
        required = [item for item in (goal_results or []) if item.required]
        if not required:
            return OverallOutcome.COMPLETED
        if any(item.status in {GoalResultStatus.UNKNOWN, GoalResultStatus.PENDING} for item in required):
            return OverallOutcome.UNKNOWN
        unsatisfied = [item for item in required if item.status == GoalResultStatus.UNSATISFIED]
        satisfied = [item for item in required if item.status == GoalResultStatus.SATISFIED]
        scheduled = [item for item in required if item.status == GoalResultStatus.SCHEDULED]
        if unsatisfied:
            return OverallOutcome.PARTIAL if satisfied else OverallOutcome.FAILED
        if scheduled:
            return OverallOutcome.PARTIAL
        return OverallOutcome.COMPLETED
