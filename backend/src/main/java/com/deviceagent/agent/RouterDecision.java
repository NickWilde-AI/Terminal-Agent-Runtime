package com.deviceagent.agent;

import com.deviceagent.domain.RouteType;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Main-agent routing payload.
 * CHAT / CLARIFY / REJECT carry reply text; FAST carries DIRECT_ACTION;
 * MULTI_AGENT carries TaskSpec fields via the bound DeviceTask.
 */
public class RouterDecision {
    public RouteType route;
    public String reply;
    public String clarifyQuestion;
    public String rejectReason;
    /** Structured direct action for FAST: capability_id + params. */
    public Map<String, Object> directAction;
    public String summary;
    public String agentRole = "MAIN";

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("route", route == null ? null : route.name());
        m.put("reply", reply);
        m.put("clarify_question", clarifyQuestion);
        m.put("reject_reason", rejectReason);
        m.put("direct_action", directAction);
        m.put("summary", summary);
        m.put("agent_role", agentRole);
        return m;
    }
}
