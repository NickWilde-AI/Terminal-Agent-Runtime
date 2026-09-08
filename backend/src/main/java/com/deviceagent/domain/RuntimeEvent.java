package com.deviceagent.domain;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class RuntimeEvent {
    private String environmentId;
    private String runId;
    private long seq;
    private Instant at;
    private Integer goalVersion;
    private String actionId;
    private String type;
    private Map<String, Object> payload = new LinkedHashMap<>();

    public String getEnvironmentId() { return environmentId; }
    public void setEnvironmentId(String environmentId) { this.environmentId = environmentId; }
    public String getRunId() { return runId; }
    public void setRunId(String runId) { this.runId = runId; }
    public long getSeq() { return seq; }
    public void setSeq(long seq) { this.seq = seq; }
    public Instant getAt() { return at; }
    public void setAt(Instant at) { this.at = at; }
    public Integer getGoalVersion() { return goalVersion; }
    public void setGoalVersion(Integer goalVersion) { this.goalVersion = goalVersion; }
    public String getActionId() { return actionId; }
    public void setActionId(String actionId) { this.actionId = actionId; }
    public String getType() { return type; }
    public void setType(String type) { this.type = type; }
    public Map<String, Object> getPayload() { return payload; }
    public void setPayload(Map<String, Object> payload) { this.payload = payload; }

    public static RuntimeEvent of(String type, Map<String, Object> payload) {
        RuntimeEvent e = new RuntimeEvent();
        e.setType(type);
        e.setAt(Ids.now());
        if (payload != null) {
            e.setPayload(new LinkedHashMap<>(payload));
        }
        return e;
    }

    public static List<RuntimeEvent> emptyList() {
        return new ArrayList<>();
    }
}
