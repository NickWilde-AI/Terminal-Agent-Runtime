package com.deviceagent.harness;

import com.deviceagent.domain.RouteType;
import com.deviceagent.model.CompiledTaskCandidate;

/**
 * Fast path: single goal, no constraints, not marked complex.
 * CHAT / CLARIFY / REJECT come from compile; everything else is MULTI_AGENT.
 */
public class ExecutionRouter {
    public RouteType route(CompiledTaskCandidate c) {
        if (c.rejectReason != null && !c.rejectReason.isBlank()) return RouteType.REJECT;
        if (c.clarifyQuestion != null && !c.clarifyQuestion.isBlank()) return RouteType.CLARIFY;
        if ("CHAT".equalsIgnoreCase(c.routeHint)) return RouteType.CHAT;
        if (isComplexHint(c.routeHint)) return RouteType.MULTI_AGENT;
        if (c.goals != null && c.goals.size() == 1
                && (c.constraints == null || c.constraints.isEmpty())) {
            return RouteType.FAST;
        }
        return RouteType.MULTI_AGENT;
    }

    private static boolean isComplexHint(String hint) {
        if (hint == null) return false;
        String h = hint.trim().toUpperCase();
        return "AGENT".equals(h) || "MULTI_AGENT".equals(h);
    }
}
