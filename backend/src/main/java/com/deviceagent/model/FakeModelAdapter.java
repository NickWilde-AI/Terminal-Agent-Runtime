package com.deviceagent.model;

import com.deviceagent.agent.MultiAgentSupport;
import com.deviceagent.agent.PlanDraft;
import com.deviceagent.agent.ReviewResult;
import com.deviceagent.agent.TaskSpec;
import com.deviceagent.domain.StateSnapshot;
import com.deviceagent.harness.GoalCompiler;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Deterministic fake model for local demos and tests. Not mixed into real API scores.
 * Delegates compile to {@link GoalCompiler}; planNext / planDraft cover registered write capabilities.
 */
@Component
@ConditionalOnProperty(prefix = "device-agent.model", name = "mode", havingValue = "fake", matchIfMissing = true)
public class FakeModelAdapter implements ModelPort {

    @Override
    public String mode() {
        return "fake";
    }

    @Override
    public CompiledTaskCandidate compileTask(
            String userText,
            StateSnapshot observation,
            List<Map<String, Object>> memoryHints
    ) {
        CompiledTaskCandidate c = GoalCompiler.compile(userText, observation, memoryHints);
        c.raw.put("model_mode", "fake");
        c.raw.put("agent_role", "MAIN");
        ModelOutputNormalizer.normalize(c, userText);
        return c;
    }

    @Override
    public PlanDraft planDraft(
            String runId,
            TaskSpec taskSpec,
            StateSnapshot observation,
            List<Map<String, Object>> priorActions,
            List<String> reviseSuggestions,
            int revisionRound
    ) {
        PlanDraft draft = MultiAgentSupport.buildPlanDraft(
                taskSpec, observation, priorActions, revisionRound, "fake");
        draft.runId = runId;
        draft.raw.put("agent_role", "PLANNER");
        draft.raw.put("revise_suggestions", reviseSuggestions == null ? List.of() : reviseSuggestions);
        return draft;
    }

    @Override
    public ReviewResult reviewPlan(String runId, TaskSpec taskSpec, PlanDraft draft) {
        ReviewResult result = MultiAgentSupport.review(taskSpec, draft, "fake");
        result.runId = runId;
        result.raw.put("agent_role", "REVIEWER");
        return result;
    }

    @Override
    public Map<String, Object> planNext(
            String runId,
            List<Map<String, Object>> goals,
            List<Map<String, Object>> constraints,
            List<Map<String, Object>> criteria,
            StateSnapshot observation,
            List<Map<String, Object>> priorActions,
            List<Map<String, Object>> memoryHints
    ) {
        TaskSpec spec = new TaskSpec();
        spec.runId = runId;
        spec.goals = goals == null ? List.of() : goals;
        spec.constraints = constraints == null ? List.of() : constraints;
        for (Map<String, Object> g : spec.goals) {
            var a = com.deviceagent.harness.TaskBinder.actionFor(g);
            if (a != null) spec.allowedCapabilities.add(String.valueOf(a.get("capability_id")));
        }
        PlanDraft draft = MultiAgentSupport.buildPlanDraft(spec, observation, priorActions, 0, "fake");
        if (draft.actions.isEmpty()) {
            return Map.of("decision", "FINISH", "reason",
                    draft.assumptions.isEmpty() ? "观察显示目标已满足或无需动作" : draft.assumptions.getFirst());
        }
        Map<String, Object> first = new LinkedHashMap<>(draft.actions.getFirst());
        first.put("decision", "ACT");
        return first;
    }
}
