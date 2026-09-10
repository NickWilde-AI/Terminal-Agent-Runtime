package com.deviceagent.agent;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Planner-agent candidate plan — never executed directly. */
public class PlanDraft {
    public List<Map<String, Object>> actions = new ArrayList<>();
    public List<Integer> order = new ArrayList<>();
    public List<Map<String, Object>> preconditions = new ArrayList<>();
    public List<Map<String, Object>> expectedEffects = new ArrayList<>();
    public List<String> assumptions = new ArrayList<>();
    public List<String> unresolved = new ArrayList<>();
    public int goalVersion;
    public String runId;
    public String agentRole = "PLANNER";
    public String modelId;
    public String promptVersion = "plandraft-v1";
    public int revisionRound;
    public Map<String, Object> raw = new LinkedHashMap<>();

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("actions", actions);
        m.put("order", order);
        m.put("preconditions", preconditions);
        m.put("expected_effects", expectedEffects);
        m.put("assumptions", assumptions);
        m.put("unresolved", unresolved);
        m.put("goal_version", goalVersion);
        m.put("run_id", runId);
        m.put("agent_role", agentRole);
        m.put("model_id", modelId);
        m.put("prompt_version", promptVersion);
        m.put("revision_round", revisionRound);
        if (!raw.isEmpty()) m.put("raw", raw);
        return m;
    }
}
