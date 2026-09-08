package com.deviceagent.domain;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class DeviceTask {
    private String runId;
    private int goalVersion = 1;
    private String rawText;
    private String defaultsRuleId = "demo-defaults-v1";
    private List<Map<String, Object>> goals = new ArrayList<>();
    private List<Map<String, Object>> constraints = new ArrayList<>();
    private List<Criterion> criteria = new ArrayList<>();
    private Map<String, Object> bindingContext = new LinkedHashMap<>();

    public String getRunId() { return runId; }
    public void setRunId(String runId) { this.runId = runId; }
    public int getGoalVersion() { return goalVersion; }
    public void setGoalVersion(int goalVersion) { this.goalVersion = goalVersion; }
    public String getRawText() { return rawText; }
    public void setRawText(String rawText) { this.rawText = rawText; }
    public String getDefaultsRuleId() { return defaultsRuleId; }
    public void setDefaultsRuleId(String defaultsRuleId) { this.defaultsRuleId = defaultsRuleId; }
    public List<Map<String, Object>> getGoals() { return goals; }
    public void setGoals(List<Map<String, Object>> goals) { this.goals = goals; }
    public List<Map<String, Object>> getConstraints() { return constraints; }
    public void setConstraints(List<Map<String, Object>> constraints) { this.constraints = constraints; }
    public List<Criterion> getCriteria() { return criteria; }
    public void setCriteria(List<Criterion> criteria) { this.criteria = criteria; }
    public Map<String, Object> getBindingContext() { return bindingContext; }
    public void setBindingContext(Map<String, Object> bindingContext) { this.bindingContext = bindingContext; }
}
