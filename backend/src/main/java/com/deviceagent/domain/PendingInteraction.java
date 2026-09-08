package com.deviceagent.domain;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public class PendingInteraction {
    private String pendingId;
    private String type; // CONFIRMATION | CLARIFICATION
    private int goalVersion;
    private String capabilityId;
    private Map<String, Object> params = new LinkedHashMap<>();
    private String question;
    private Instant expiresAt;
    private String sourceMessageId;

    public String getPendingId() { return pendingId; }
    public void setPendingId(String pendingId) { this.pendingId = pendingId; }
    public String getType() { return type; }
    public void setType(String type) { this.type = type; }
    public int getGoalVersion() { return goalVersion; }
    public void setGoalVersion(int goalVersion) { this.goalVersion = goalVersion; }
    public String getCapabilityId() { return capabilityId; }
    public void setCapabilityId(String capabilityId) { this.capabilityId = capabilityId; }
    public Map<String, Object> getParams() { return params; }
    public void setParams(Map<String, Object> params) { this.params = params; }
    public String getQuestion() { return question; }
    public void setQuestion(String question) { this.question = question; }
    public Instant getExpiresAt() { return expiresAt; }
    public void setExpiresAt(Instant expiresAt) { this.expiresAt = expiresAt; }
    public String getSourceMessageId() { return sourceMessageId; }
    public void setSourceMessageId(String sourceMessageId) { this.sourceMessageId = sourceMessageId; }

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("pending_id", pendingId);
        m.put("pendingId", pendingId);
        m.put("type", type);
        m.put("goal_version", goalVersion);
        m.put("goalVersion", goalVersion);
        m.put("capability_id", capabilityId);
        m.put("capabilityId", capabilityId);
        m.put("params", params);
        m.put("question", question);
        m.put("expires_at", expiresAt);
        m.put("expiresAt", expiresAt);
        return m;
    }
}
