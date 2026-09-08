package com.deviceagent.memory;

import com.deviceagent.domain.StateSnapshot;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Minimal context injection for each model decision (docs/03 §14.2).
 */
@Component
public class ContextBuilder {
    private final MemoryRetriever retriever;

    public ContextBuilder(MemoryRetriever retriever) {
        this.retriever = retriever;
    }

    public BuiltContext build(
            String sessionId,
            String userText,
            List<Map<String, Object>> goals,
            List<Map<String, Object>> constraints,
            List<Map<String, Object>> criteria,
            StateSnapshot observation,
            List<Map<String, Object>> priorActions
    ) {
        List<MemoryEntry> memories = retriever.retrieve(sessionId, userText, goals);
        List<Map<String, Object>> hints = new ArrayList<>();
        for (MemoryEntry m : memories) {
            hints.add(m.toHint());
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("goals", goals == null ? List.of() : goals);
        payload.put("constraints", constraints == null ? List.of() : constraints);
        payload.put("criteria", criteria == null ? List.of() : criteria);
        payload.put("observation", observation == null ? Map.of() : observation.getState());
        payload.put("prior_actions_summary", summarizeActions(priorActions));
        payload.put("long_term_memory", hints);
        payload.put("token_budget_note", "minimal_context_v1");
        int approxTokens = estimateTokens(payload);
        payload.put("approx_tokens", approxTokens);
        return new BuiltContext(payload, memories, hints, approxTokens);
    }

    public BuiltContext buildForCompile(String sessionId, String userText, StateSnapshot observation) {
        return build(sessionId, userText, List.of(), List.of(), List.of(), observation, List.of());
    }

    private List<Map<String, Object>> summarizeActions(List<Map<String, Object>> priorActions) {
        if (priorActions == null) return List.of();
        List<Map<String, Object>> out = new ArrayList<>();
        int from = Math.max(0, priorActions.size() - 6);
        for (int i = from; i < priorActions.size(); i++) {
            Map<String, Object> a = priorActions.get(i);
            Map<String, Object> s = new LinkedHashMap<>();
            s.put("capability_id", a.get("capability_id"));
            s.put("execution_status", a.get("execution_status"));
            s.put("params", a.get("params"));
            out.add(s);
        }
        return out;
    }

    private int estimateTokens(Map<String, Object> payload) {
        return Math.max(1, String.valueOf(payload).length() / 3);
    }

    public record BuiltContext(
            Map<String, Object> payload,
            List<MemoryEntry> memories,
            List<Map<String, Object>> hints,
            int approxTokens
    ) {}
}
