package com.deviceagent.agent;

import com.deviceagent.domain.ReviewDecision;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Reviewer-agent semantic check — cannot mark a run COMPLETED. */
public class ReviewResult {
    public ReviewDecision decision = ReviewDecision.REJECT;
    public List<String> missingGoals = new ArrayList<>();
    public List<String> violatedConstraints = new ArrayList<>();
    public List<String> riskyActions = new ArrayList<>();
    public List<String> evidenceGaps = new ArrayList<>();
    public List<String> suggestions = new ArrayList<>();
    public int goalVersion;
    public String runId;
    public String agentRole = "REVIEWER";
    public String modelId;
    public String promptVersion = "review-v1";
    public Map<String, Object> raw = new LinkedHashMap<>();

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("decision", decision == null ? null : decision.name());
        m.put("missing_goals", missingGoals);
        m.put("violated_constraints", violatedConstraints);
        m.put("risky_actions", riskyActions);
        m.put("evidence_gaps", evidenceGaps);
        m.put("suggestions", suggestions);
        m.put("goal_version", goalVersion);
        m.put("run_id", runId);
        m.put("agent_role", agentRole);
        m.put("model_id", modelId);
        m.put("prompt_version", promptVersion);
        if (!raw.isEmpty()) m.put("raw", raw);
        return m;
    }
}
