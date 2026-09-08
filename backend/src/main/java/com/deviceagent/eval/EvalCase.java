package com.deviceagent.eval;

import java.util.List;
import java.util.Map;

public class EvalCase {
    public String id;
    public String category;
    public boolean completable;
    public String request;
    public String expectedRoute;
    public List<String> allowedLifecycles;
    public Map<String, Object> initialState;
    public Map<String, Object> finalStateEquals;
    public List<String> forbidCapabilities;
    public boolean requireNoWrites;
    public String requireAppliedCapability;
    public String faultType;
    public String faultCapability;
    public int faultTimes = 1;
    public String clarifyAnswer;
    public String interveneText;
    public boolean cancel;
    public Map<String, Object> externalAfterCompile;
    public String candidateCapability;
    public Map<String, Object> candidateParams;
    public List<Map<String, Object>> constraints;
    public boolean expectDeny;
    /** 评测时临时打开写确认；配合 confirmDecision。 */
    public boolean requireConfirmation;
    /** APPROVE | REJECT */
    public String confirmDecision;
    /** I06：澄清等待人为过期 */
    public boolean forceClarifyTimeout;

    public static EvalCase of(String id, String category, boolean completable) {
        EvalCase c = new EvalCase();
        c.id = id;
        c.category = category;
        c.completable = completable;
        return c;
    }
}
