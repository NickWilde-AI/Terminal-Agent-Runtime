package com.deviceagent.agent;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Main-agent output for the multi-agent path. */
public class TaskSpec {
    public String goal;
    public List<Map<String, Object>> goals = new ArrayList<>();
    public List<Map<String, Object>> constraints = new ArrayList<>();
    public List<Map<String, Object>> contextRefs = new ArrayList<>();
    public List<Map<String, Object>> successCriteria = new ArrayList<>();
    public List<String> allowedCapabilities = new ArrayList<>();
    public int goalVersion;
    public String runId;
    public String modelId;
    public String promptVersion = "taskspec-v1";

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("goal", goal);
        m.put("goals", goals);
        m.put("constraints", constraints);
        m.put("context_refs", contextRefs);
        m.put("success_criteria", successCriteria);
        m.put("allowed_capabilities", allowedCapabilities);
        m.put("goal_version", goalVersion);
        m.put("run_id", runId);
        m.put("model_id", modelId);
        m.put("prompt_version", promptVersion);
        return m;
    }
}
