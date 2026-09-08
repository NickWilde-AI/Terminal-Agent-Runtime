package com.deviceagent.model;

import com.deviceagent.domain.StateSnapshot;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public interface ModelPort {
    String mode();

    default CompiledTaskCandidate compileTask(String userText, StateSnapshot observation) {
        return compileTask(userText, observation, List.of());
    }

    CompiledTaskCandidate compileTask(
            String userText,
            StateSnapshot observation,
            List<Map<String, Object>> memoryHints
    );

    default Map<String, Object> planNext(
            String runId,
            List<Map<String, Object>> goals,
            List<Map<String, Object>> constraints,
            List<Map<String, Object>> criteria,
            StateSnapshot observation,
            List<Map<String, Object>> priorActions
    ) {
        return planNext(runId, goals, constraints, criteria, observation, priorActions, List.of());
    }

    Map<String, Object> planNext(
            String runId,
            List<Map<String, Object>> goals,
            List<Map<String, Object>> constraints,
            List<Map<String, Object>> criteria,
            StateSnapshot observation,
            List<Map<String, Object>> priorActions,
            List<Map<String, Object>> memoryHints
    );

    /** Bind subsequent model turns to a goal version / deadline (no-op for Fake). */
    default void requestContext(String runId, int goalVersion, Instant deadline) {}

    /** Feed tool/device evidence back to the model session (no-op for Fake / JSON adapters). */
    default void feedback(String runId, int goalVersion, Map<String, Object> plan, Map<String, Object> result) {}
}
