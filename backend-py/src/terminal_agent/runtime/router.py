"""Deterministic FAST / MULTI_AGENT execution routing."""

from terminal_agent.contracts import CompiledTaskCandidate, RouteType


class ExecutionRouter:
    def route(self, candidate: CompiledTaskCandidate) -> RouteType:
        if candidate.reject_reason and candidate.reject_reason.strip():
            return RouteType.REJECT
        if candidate.clarify_question and candidate.clarify_question.strip():
            return RouteType.CLARIFY
        hint = (candidate.route_hint or "").strip().upper()
        if hint == "CHAT":
            return RouteType.CHAT
        if hint in ("AGENT", "MULTI_AGENT"):
            return RouteType.MULTI_AGENT
        if len(candidate.goals) == 1 and not candidate.constraints:
            return RouteType.FAST
        return RouteType.MULTI_AGENT
