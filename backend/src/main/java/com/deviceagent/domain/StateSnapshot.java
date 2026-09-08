package com.deviceagent.domain;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public class StateSnapshot {
    private long revision;
    private Map<String, Map<String,Object>> origins = new LinkedHashMap<>();
    public long getRevision() { return revision; }
    public void setRevision(long revision) { this.revision = revision; }
    public Map<String, Map<String,Object>> getOrigins() { return origins; }
    public void setOrigins(Map<String, Map<String,Object>> origins) { this.origins = origins; }
    private String deviceId;
    private String environmentId;
    private Map<String, Long> domainRevisions = new LinkedHashMap<>();
    private Instant observedAt;
    private Map<String, Object> state = new LinkedHashMap<>();
    private ChangeSource changeSource = ChangeSource.UNKNOWN;
    private String actionId;

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }
    public String getEnvironmentId() { return environmentId; }
    public void setEnvironmentId(String environmentId) { this.environmentId = environmentId; }
    public Map<String, Long> getDomainRevisions() { return domainRevisions; }
    public void setDomainRevisions(Map<String, Long> domainRevisions) { this.domainRevisions = domainRevisions; }
    public Instant getObservedAt() { return observedAt; }
    public void setObservedAt(Instant observedAt) { this.observedAt = observedAt; }
    public Map<String, Object> getState() { return state; }
    public void setState(Map<String, Object> state) { this.state = state; }
    public ChangeSource getChangeSource() { return changeSource; }
    public void setChangeSource(ChangeSource changeSource) { this.changeSource = changeSource; }
    public String getActionId() { return actionId; }
    public void setActionId(String actionId) { this.actionId = actionId; }
}
