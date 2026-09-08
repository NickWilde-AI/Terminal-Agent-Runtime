package com.deviceagent.domain;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class RunRecord {
    private String runId;
    private String requestId;
    private String deviceId;
    private String environmentId;
    private String sessionId;
    private RunLifecycle lifecycle = RunLifecycle.RECEIVED;
    private RunPhase phase = RunPhase.COMPILE;
    private RouteType routeType;
    private String stopReason;
    private String resultSummary;
    private GoalOutcome goalOutcome;
    private DeviceTask task = new DeviceTask();
    private Budget budget = new Budget();
    private List<ToolAction> actions = new ArrayList<>();
    private List<RuntimeEvent> events = new ArrayList<>();
    private Map<String, Object> evaluationSnapshot = new LinkedHashMap<>();
    private Instant createdAt = Ids.now();
    private Instant updatedAt = Ids.now();
    private volatile boolean cancelAccepted;
    private String inFlightActionId;
    private boolean unresolvedUnknown;
    private PendingInteraction pending;

    public String getRunId() { return runId; }
    public void setRunId(String runId) { this.runId = runId; }
    public String getRequestId() { return requestId; }
    public void setRequestId(String requestId) { this.requestId = requestId; }
    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }
    public String getEnvironmentId() { return environmentId; }
    public void setEnvironmentId(String environmentId) { this.environmentId = environmentId; }
    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public RunLifecycle getLifecycle() { return lifecycle; }
    public void setLifecycle(RunLifecycle lifecycle) { this.lifecycle = lifecycle; }
    public RunPhase getPhase() { return phase; }
    public void setPhase(RunPhase phase) { this.phase = phase; }
    public RouteType getRouteType() { return routeType; }
    public void setRouteType(RouteType routeType) { this.routeType = routeType; }
    public String getStopReason() { return stopReason; }
    public void setStopReason(String stopReason) { this.stopReason = stopReason; }
    public String getResultSummary() { return resultSummary; }
    public void setResultSummary(String resultSummary) { this.resultSummary = resultSummary; }
    public GoalOutcome getGoalOutcome() { return goalOutcome; }
    public void setGoalOutcome(GoalOutcome goalOutcome) { this.goalOutcome = goalOutcome; }
    public DeviceTask getTask() { return task; }
    public void setTask(DeviceTask task) { this.task = task; }
    public Budget getBudget() { return budget; }
    public void setBudget(Budget budget) { this.budget = budget; }
    public List<ToolAction> getActions() { return actions; }
    public void setActions(List<ToolAction> actions) { this.actions = actions; }
    public List<RuntimeEvent> getEvents() { return events; }
    public void setEvents(List<RuntimeEvent> events) { this.events = events; }
    public Map<String, Object> getEvaluationSnapshot() { return evaluationSnapshot; }
    public void setEvaluationSnapshot(Map<String, Object> evaluationSnapshot) { this.evaluationSnapshot = evaluationSnapshot; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }
    public boolean isCancelAccepted() { return cancelAccepted; }
    public void setCancelAccepted(boolean cancelAccepted) { this.cancelAccepted = cancelAccepted; }
    public String getInFlightActionId() { return inFlightActionId; }
    public void setInFlightActionId(String inFlightActionId) { this.inFlightActionId = inFlightActionId; }
    public boolean isUnresolvedUnknown() { return unresolvedUnknown; }
    public void setUnresolvedUnknown(boolean unresolvedUnknown) { this.unresolvedUnknown = unresolvedUnknown; }
    public PendingInteraction getPending() { return pending; }
    public void setPending(PendingInteraction pending) { this.pending = pending; }

    public boolean isTerminal() {
        return switch (lifecycle) {
            case COMPLETED, PARTIAL, FAILED, STOPPED, CANCELLED, TIMED_OUT, INTERRUPTED -> true;
            default -> false;
        };
    }

    public void touch() {
        this.updatedAt = Ids.now();
    }
}
