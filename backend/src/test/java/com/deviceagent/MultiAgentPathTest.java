package com.deviceagent;

import com.deviceagent.agent.MultiAgentSupport;
import com.deviceagent.agent.PlanDraft;
import com.deviceagent.agent.TaskSpec;
import com.deviceagent.domain.ReviewDecision;
import com.deviceagent.domain.RouteType;
import com.deviceagent.domain.RunLifecycle;
import com.deviceagent.domain.StateSnapshot;
import com.deviceagent.harness.HarnessService;
import com.deviceagent.store.InMemoryRunStore;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MultiAgentPathTest {

    @Autowired
    HarnessService harness;
    @Autowired
    InMemoryRunStore store;

    @Test
    void chatDoesNotCallTools() {
        var run = harness.createRun(null, "你好", "test-chat");
        assertEquals(RouteType.CHAT, run.getRouteType());
        assertEquals(RunLifecycle.COMPLETED, run.getLifecycle());
        assertTrue(run.getActions().isEmpty());
        assertTrue(run.getResultSummary() != null && run.getResultSummary().contains("你好")
                || run.getResultSummary().contains("Agent"));
    }

    @Test
    void fastPathOnlyMainAgentNoPlanDraft() {
        var run = harness.createRun(null, "把空调设为 23 度", "test-fast");
        assertEquals(RouteType.FAST, run.getRouteType());
        assertEquals(RunLifecycle.COMPLETED, run.getLifecycle());
        boolean hasPlanDraft = store.eventsAfter(run.getRunId(), 0).stream()
                .anyMatch(e -> "PLAN_DRAFT".equals(e.getType()) || "REVIEW_RESULT".equals(e.getType()));
        assertFalse(hasPlanDraft, "FAST must not enter planner/reviewer");
        boolean hasMain = store.eventsAfter(run.getRunId(), 0).stream()
                .anyMatch(e -> "MODEL_REQUEST".equals(e.getType())
                        && "MAIN".equals(String.valueOf(e.getPayload().get("agent_role"))));
        assertTrue(hasMain || store.eventsAfter(run.getRunId(), 0).stream()
                .anyMatch(e -> "COMPILE".equals(e.getType())));
    }

    @Test
    void complexPathEmitsThreeAgentTrace() {
        var run = harness.createRun(null,
                "后排要休息，把座舱调整舒服一点；媒体声音调低，但保留导航提示，不要开窗。",
                "test-multi");
        assertEquals(RouteType.MULTI_AGENT, run.getRouteType());
        var events = store.eventsAfter(run.getRunId(), 0);
        assertTrue(events.stream().anyMatch(e -> "TASK_SPEC".equals(e.getType())));
        assertTrue(events.stream().anyMatch(e -> "PLAN_DRAFT".equals(e.getType())));
        assertTrue(events.stream().anyMatch(e -> "REVIEW_RESULT".equals(e.getType())));
        assertTrue(events.stream().anyMatch(e ->
                "MODEL_REQUEST".equals(e.getType()) && "PLANNER".equals(String.valueOf(e.getPayload().get("agent_role")))));
        assertTrue(events.stream().anyMatch(e ->
                "MODEL_REQUEST".equals(e.getType()) && "REVIEWER".equals(String.valueOf(e.getPayload().get("agent_role")))));
        assertFalse(run.getActions().stream().anyMatch(a ->
                String.valueOf(a.getCapabilityId()).startsWith("window.")),
                "no_window constraint must block window writes");
    }

    @Test
    void reviewerRejectsConstraintViolation() {
        TaskSpec spec = new TaskSpec();
        spec.goals = List.of(Map.of("type", "window_position", "window", "front_left", "position", 50));
        spec.constraints = List.of(Map.of("type", "no_window"));
        spec.allowedCapabilities = List.of("window.set_position");
        PlanDraft draft = new PlanDraft();
        draft.actions.add(Map.of("capability_id", "window.set_position",
                "params", Map.of("window", "front_left", "position", 50)));
        var review = MultiAgentSupport.review(spec, draft, "fake");
        assertEquals(ReviewDecision.REJECT, review.decision);
        assertFalse(review.violatedConstraints.isEmpty());
    }

    @Test
    void reviewerRevisesMissingGoals() {
        TaskSpec spec = new TaskSpec();
        spec.goals = List.of(
                Map.of("type", "cabin_temperature", "value", 23),
                Map.of("type", "media_volume", "value", 3)
        );
        spec.allowedCapabilities = List.of("climate.set_temperature", "media.set_volume");
        PlanDraft draft = MultiAgentSupport.buildPlanDraft(
                spec, new StateSnapshot(), List.of(), 0, "fake");
        PlanDraft omitted = MultiAgentSupport.omitClimateActions(draft);
        // Ensure media action remains so missing climate is detected
        if (omitted.actions.isEmpty()) {
            omitted.actions.add(Map.of("capability_id", "media.set_volume", "params", Map.of("value", 3)));
        }
        var review = MultiAgentSupport.review(spec, omitted, "fake");
        assertEquals(ReviewDecision.REVISE, review.decision);
        assertFalse(review.missingGoals.isEmpty());
    }

    @Test
    void cancelDropsLatePlanDraft() throws Exception {
        harness.armEvalPauseAfterGoalBound();
        try {
            var run = harness.createRun(null,
                    "打开空调，设为23度；播放周杰伦；然后导航到虹桥机场。",
                    "test-cancel", false);
            // Wait until GOAL_BOUND / pause
            long end = System.currentTimeMillis() + 5000;
            while (System.currentTimeMillis() < end && run.getTask().getGoals().isEmpty()) {
                Thread.sleep(20);
            }
            harness.cancel(run.getRunId());
            harness.releaseEvalPause();
            harness.awaitIdle(3000);
            var refreshed = store.find(run.getRunId()).orElseThrow();
            assertEquals(RunLifecycle.CANCELLED, refreshed.getLifecycle());
            // Any PLAN_DRAFT after cancel must be discarded or absent after cancel accepted
            boolean planAfterCancel = false;
            boolean cancelSeen = false;
            for (var e : store.eventsAfter(run.getRunId(), 0)) {
                if ("CANCEL_ACCEPTED".equals(e.getType())) cancelSeen = true;
                if (cancelSeen && "PLAN_DRAFT".equals(e.getType())) planAfterCancel = true;
            }
            assertTrue(cancelSeen);
            assertFalse(planAfterCancel, "late PlanDraft must not be recorded after cancel");
        } finally {
            harness.releaseEvalPause();
        }
    }
}
