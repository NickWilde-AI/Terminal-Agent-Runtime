package com.deviceagent.domain;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public class Budget {
    private Instant deadline;
    private int maxModelCalls = 12;
    private int maxToolCalls = 24;
    private int maxWriteActions = 6;
    private int maxReplans = 2;
    private int maxSameFailure = 2;
    private final AtomicInteger modelCalls = new AtomicInteger();
    private final AtomicInteger toolCalls = new AtomicInteger();
    private final AtomicInteger writeActions = new AtomicInteger();
    private final AtomicInteger replans = new AtomicInteger();
    private final AtomicInteger sameFailure = new AtomicInteger();

    public Instant getDeadline() { return deadline; }
    public void setDeadline(Instant deadline) { this.deadline = deadline; }
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
    public int getModelCalls() { return modelCalls.get(); }
    public int getToolCalls() { return toolCalls.get(); }
    public int getWriteActions() { return writeActions.get(); }
    public int getReplans() { return replans.get(); }
    public int getSameFailure() { return sameFailure.get(); }

    public boolean expired() {
        return deadline != null && Instant.now().isAfter(deadline);
    }

    public void countModel() {
        if(expired() || modelCalls.get() >= maxModelCalls) throw new IllegalStateException("BUDGET_EXHAUSTED_MODEL");
        modelCalls.incrementAndGet();
    }

    public void countTool() {
        if(expired() || toolCalls.get() >= maxToolCalls) throw new IllegalStateException("BUDGET_EXHAUSTED_TOOL");
        toolCalls.incrementAndGet();
    }

    public void countWrite() {
        if(expired() || writeActions.get() >= maxWriteActions) throw new IllegalStateException("BUDGET_EXHAUSTED_WRITE");
        writeActions.incrementAndGet();
    }

    public void countReplan() {
        if (expired() || replans.incrementAndGet() > maxReplans) {
            throw new IllegalStateException("BUDGET_EXHAUSTED_REPLAN");
        }
    }

    public void countSameFailure() {
        if (expired() || sameFailure.incrementAndGet() > maxSameFailure) {
            throw new IllegalStateException("BUDGET_EXHAUSTED_SAME_FAILURE");
        }
    }

    public void resetSameFailure() {
        sameFailure.set(0);
    }

    public String checkExhausted() {
        if (expired()) return "TIMED_OUT";
        if (modelCalls.get() > maxModelCalls) return "BUDGET_EXHAUSTED_MODEL";
        if (toolCalls.get() > maxToolCalls) return "BUDGET_EXHAUSTED_TOOL";
        if (writeActions.get() > maxWriteActions) return "BUDGET_EXHAUSTED_WRITE";
        if (replans.get() > maxReplans) return "BUDGET_EXHAUSTED_REPLAN";
        if (sameFailure.get() > maxSameFailure) return "BUDGET_EXHAUSTED_SAME_FAILURE";
        return null;
    }

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("deadline", deadline);
        m.put("modelCalls", modelCalls.get());
        m.put("maxModelCalls", maxModelCalls);
        m.put("toolCalls", toolCalls.get());
        m.put("maxToolCalls", maxToolCalls);
        m.put("writeActions", writeActions.get());
        m.put("maxWriteActions", maxWriteActions);
        m.put("replans", replans.get());
        m.put("maxReplans", maxReplans);
        m.put("sameFailure", sameFailure.get());
        m.put("maxSameFailure", maxSameFailure);
        return m;
    }

    public List<String> labels() {
        List<String> labels = new ArrayList<>();
        labels.add("model=" + modelCalls.get() + "/" + maxModelCalls);
        labels.add("tool=" + toolCalls.get() + "/" + maxToolCalls);
        labels.add("write=" + writeActions.get() + "/" + maxWriteActions);
        return labels;
    }
}
