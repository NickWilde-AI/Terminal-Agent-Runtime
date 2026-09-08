package com.deviceagent.domain;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public class ToolAction {
    private String actionId;
    private String idempotencyKey;
    private String runId;
    private int goalVersion;
    private String environmentId;
    private String capabilityId;
    private Map<String, Object> params = new LinkedHashMap<>();
    private Map<String, Long> expectedRevisions = new LinkedHashMap<>();
    private Instant preparedAt;
    private Instant dispatchedAt;
    private Instant finishedAt;
    private Instant deadline;
    private ExecutionStatus executionStatus = ExecutionStatus.PREPARED;
    private VerificationStatus verificationStatus;
    private Attribution attribution = Attribution.UNKNOWN;
    private String retryOf;
    private String message;
    private Map<String, Object> evidence = new LinkedHashMap<>();

    public String getActionId() { return actionId; }
    public void setActionId(String actionId) { this.actionId = actionId; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public void setIdempotencyKey(String idempotencyKey) { this.idempotencyKey = idempotencyKey; }
    public String getRunId() { return runId; }
    public void setRunId(String runId) { this.runId = runId; }
    public int getGoalVersion() { return goalVersion; }
    public void setGoalVersion(int goalVersion) { this.goalVersion = goalVersion; }
    public String getEnvironmentId() { return environmentId; }
    public void setEnvironmentId(String environmentId) { this.environmentId = environmentId; }
    public String getCapabilityId() { return capabilityId; }
    public void setCapabilityId(String capabilityId) { this.capabilityId = capabilityId; }
    public Map<String, Object> getParams() { return params; }
    public void setParams(Map<String, Object> params) { this.params = params; }
    public Map<String, Long> getExpectedRevisions() { return expectedRevisions; }
    public void setExpectedRevisions(Map<String, Long> expectedRevisions) { this.expectedRevisions = expectedRevisions; }
    public Instant getPreparedAt() { return preparedAt; }
    public void setPreparedAt(Instant preparedAt) { this.preparedAt = preparedAt; }
    public Instant getDispatchedAt() { return dispatchedAt; }
    public void setDispatchedAt(Instant dispatchedAt) { this.dispatchedAt = dispatchedAt; }
    public Instant getFinishedAt() { return finishedAt; }
    public void setFinishedAt(Instant finishedAt) { this.finishedAt = finishedAt; }
    public Instant getDeadline() { return deadline; }
    public void setDeadline(Instant deadline) { this.deadline = deadline; }
    public ExecutionStatus getExecutionStatus() { return executionStatus; }
    public void setExecutionStatus(ExecutionStatus executionStatus) { this.executionStatus = executionStatus; }
    public VerificationStatus getVerificationStatus() { return verificationStatus; }
    public void setVerificationStatus(VerificationStatus verificationStatus) { this.verificationStatus = verificationStatus; }
    public Attribution getAttribution() { return attribution; }
    public void setAttribution(Attribution attribution) { this.attribution = attribution; }
    public String getRetryOf() { return retryOf; }
    public void setRetryOf(String retryOf) { this.retryOf = retryOf; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
    public Map<String, Object> getEvidence() { return evidence; }
    public void setEvidence(Map<String, Object> evidence) { this.evidence = evidence; }
}
