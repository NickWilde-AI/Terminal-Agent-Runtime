package com.deviceagent.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "device-agent")
public class DeviceAgentProperties {
    private String defaultsRuleId = "demo-defaults-v1";
    private long freshWindowMs = 2000;
    private BudgetProps budget = new BudgetProps();
    private ModelProps model = new ModelProps();
    private String eventLogDir = "./data/events";
    private boolean requireConfirmation;
    private String persistence = "sqlite";
    private String sqlitePath = "./data/harness.db";

    public String getDefaultsRuleId() { return defaultsRuleId; }
    public void setDefaultsRuleId(String defaultsRuleId) { this.defaultsRuleId = defaultsRuleId; }
    public long getFreshWindowMs() { return freshWindowMs; }
    public void setFreshWindowMs(long freshWindowMs) { this.freshWindowMs = freshWindowMs; }
    public BudgetProps getBudget() { return budget; }
    public void setBudget(BudgetProps budget) { this.budget = budget; }
    public ModelProps getModel() { return model; }
    public void setModel(ModelProps model) { this.model = model; }
    public String getEventLogDir() { return eventLogDir; }
    public void setEventLogDir(String eventLogDir) { this.eventLogDir = eventLogDir; }
    public boolean isRequireConfirmation() { return requireConfirmation; }
    public void setRequireConfirmation(boolean requireConfirmation) { this.requireConfirmation = requireConfirmation; }
    public String getPersistence() { return persistence; }
    public void setPersistence(String persistence) { this.persistence = persistence; }
    public String getSqlitePath() { return sqlitePath; }
    public void setSqlitePath(String sqlitePath) { this.sqlitePath = sqlitePath; }

    public static class BudgetProps {
        private int absoluteDeadlineSeconds = 120;
        private int maxModelCalls = 12;
        private int maxToolCalls = 24;
        private int maxWriteActions = 6;
        private int maxReplans = 2;
        private int maxSameFailure = 2;

        public int getAbsoluteDeadlineSeconds() { return absoluteDeadlineSeconds; }
        public void setAbsoluteDeadlineSeconds(int absoluteDeadlineSeconds) { this.absoluteDeadlineSeconds = absoluteDeadlineSeconds; }
        public int getMaxModelCalls() { return maxModelCalls; }
        public void setMaxModelCalls(int maxModelCalls) { this.maxModelCalls = maxModelCalls; }
        public int getMaxToolCalls() { return maxToolCalls; }
        public void setMaxToolCalls(int maxToolCalls) { this.maxToolCalls = maxToolCalls; }
        public int getMaxWriteActions() { return maxWriteActions; }
        public void setMaxWriteActions(int maxWriteActions) { this.maxWriteActions = maxWriteActions; }
        public int getMaxReplans() { return maxReplans; }
        public void setMaxReplans(int maxReplans) { this.maxReplans = maxReplans; }
        public int getMaxSameFailure() { return maxSameFailure; }
        public void setMaxSameFailure(int maxSameFailure) { this.maxSameFailure = maxSameFailure; }
    }

    public static class ModelProps {
        private String mode = "fake";
        private String baseUrl = "";
        private String apiKey = "";
        private String modelId = "step-3.5-flash";
        /** Design-only edge label; not a real NPU deployment. */
        private String edgeModelId = "step-edge-stub";
        /** cloud | edge — same task/tool protocol, different model id label. */
        private String placement = "cloud";
        private long timeoutMs = 30000;

        public String getMode() { return mode; }
        public void setMode(String mode) { this.mode = mode; }
        public String getBaseUrl() { return baseUrl; }
        public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }
        public String getApiKey() { return apiKey; }
        public void setApiKey(String apiKey) { this.apiKey = apiKey; }
        public String getModelId() { return modelId; }
        public void setModelId(String modelId) { this.modelId = modelId; }
        public String getEdgeModelId() { return edgeModelId; }
        public void setEdgeModelId(String edgeModelId) { this.edgeModelId = edgeModelId; }
        public String getPlacement() { return placement; }
        public void setPlacement(String placement) { this.placement = placement; }
        public long getTimeoutMs() { return timeoutMs; }
        public void setTimeoutMs(long timeoutMs) { this.timeoutMs = timeoutMs; }
    }
}
