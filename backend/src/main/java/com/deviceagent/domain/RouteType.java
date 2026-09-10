package com.deviceagent.domain;

public enum RouteType {
    CHAT,
    FAST,
    /** @deprecated Prefer {@link #MULTI_AGENT}; kept for older traces/tests that still say AGENT. */
    AGENT,
    MULTI_AGENT,
    CLARIFY,
    REJECT;

    public boolean isComplexAgent() {
        return this == MULTI_AGENT || this == AGENT;
    }
}
