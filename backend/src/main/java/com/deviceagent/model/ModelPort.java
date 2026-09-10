package com.deviceagent.model;

import com.deviceagent.agent.PlanDraft;
import com.deviceagent.agent.ReviewResult;
import com.deviceagent.agent.TaskSpec;
import com.deviceagent.domain.AgentRole;
import com.deviceagent.domain.StateSnapshot;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public interface ModelPort {
    String mode();

    default CompiledTaskCandidate compileTask(String userText, StateSnapshot observation) {
        return compileTask(userText, observation, List.of());
    }

    /** Main-agent compile / route understanding. */
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

    /** Legacy single-step planner (still used by baseline / FAST fallback). */
    Map<String, Object> planNext(
            String runId,
            List<Map<String, Object>> goals,
            List<Map<String, Object>> constraints,
            List<Map<String, Object>> criteria,
            StateSnapshot observation,
            List<Map<String, Object>> priorActions,
            List<Map<String, Object>> memoryHints
    );

    /** Planner agent: full PlanDraft for MULTI_AGENT path. */
    default PlanDraft planDraft(
            String runId,
            TaskSpec taskSpec,
            StateSnapshot observation,
            List<Map<String, Object>> priorActions,
            List<String> reviseSuggestions,
            int revisionRound
    ) {
        throw new UnsupportedOperationException("planDraft not implemented");
    }

    /** Reviewer agent: semantic check of PlanDraft against TaskSpec. */
    default ReviewResult reviewPlan(String runId, TaskSpec taskSpec, PlanDraft draft) {
        throw new UnsupportedOperationException("reviewPlan not implemented");
    }

    /** Bind subsequent model turns to a goal version / deadline (no-op for Fake). */
    default void requestContext(String runId, int goalVersion, Instant deadline) {}

    default void requestContext(String runId, AgentRole role, int goalVersion, Instant deadline) {
        requestContext(runId, goalVersion, deadline);
    }

    /** Feed tool/device evidence back to the model session (no-op for Fake / JSON adapters). */
    default void feedback(String runId, int goalVersion, Map<String, Object> plan, Map<String, Object> result) {}
}
