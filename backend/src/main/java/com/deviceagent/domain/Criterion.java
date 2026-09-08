package com.deviceagent.domain;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public class Criterion {
    private String criterionId;
    private String templateId;
    private Map<String, Object> params = new LinkedHashMap<>();
    private boolean required = true;
    private String sourceRef;
    private Map<String, Object> baselineObservation = new LinkedHashMap<>();
    private int boundGoalVersion;
    private Instant boundAt;

    public String getCriterionId() { return criterionId; }
    public void setCriterionId(String criterionId) { this.criterionId = criterionId; }
    public String getTemplateId() { return templateId; }
    public void setTemplateId(String templateId) { this.templateId = templateId; }
    public Map<String, Object> getParams() { return params; }
    public void setParams(Map<String, Object> params) { this.params = params; }
    public boolean isRequired() { return required; }
    public void setRequired(boolean required) { this.required = required; }
    public String getSourceRef() { return sourceRef; }
    public void setSourceRef(String sourceRef) { this.sourceRef = sourceRef; }
    public Map<String, Object> getBaselineObservation() { return baselineObservation; }
    public void setBaselineObservation(Map<String, Object> baselineObservation) { this.baselineObservation = baselineObservation; }
    public int getBoundGoalVersion() { return boundGoalVersion; }
    public void setBoundGoalVersion(int boundGoalVersion) { this.boundGoalVersion = boundGoalVersion; }
    public Instant getBoundAt() { return boundAt; }
    public void setBoundAt(Instant boundAt) { this.boundAt = boundAt; }
}
