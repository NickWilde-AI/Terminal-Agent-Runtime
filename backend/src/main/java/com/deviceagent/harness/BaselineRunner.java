package com.deviceagent.harness;

import com.deviceagent.domain.DeviceDomain;
import com.deviceagent.domain.ExecutionStatus;
import com.deviceagent.domain.GoalOutcome;
import com.deviceagent.domain.Ids;
import com.deviceagent.domain.RouteType;
import com.deviceagent.domain.RunLifecycle;
import com.deviceagent.domain.RunPhase;
import com.deviceagent.domain.RunRecord;
import com.deviceagent.domain.StateSnapshot;
import com.deviceagent.domain.ToolAction;
import com.deviceagent.model.CompiledTaskCandidate;
import com.deviceagent.model.ModelPort;
import com.deviceagent.simulator.DeviceSimulator;
import com.deviceagent.store.InMemoryRunStore;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;

/**
 * Baseline：编译后一次性确定性展开目标为动作，不调用 planNext、不回传工具结果。
 * 这是「单次确定性展开」对照，不是纯 Function Calling one-shot；报告中按此命名。
 */
@Service
public class BaselineRunner {
    private final InMemoryRunStore runStore;
    private final DeviceSimulator simulator;
    private final ModelPort modelPort;
    private final TaskBinder taskBinder;
    private final CapabilityExecutor executor;
    private final Verifier verifier;
    private final com.deviceagent.config.DeviceAgentProperties properties;
    private final com.deviceagent.store.SqlitePersistence sqlitePersistence;

    public BaselineRunner(
            InMemoryRunStore runStore,
            DeviceSimulator simulator,
            ModelPort modelPort,
            TaskBinder taskBinder,
            CapabilityExecutor executor,
            Verifier verifier,
            com.deviceagent.config.DeviceAgentProperties properties,
            com.deviceagent.store.SqlitePersistence sqlitePersistence
    ) {
        this.runStore = runStore;
        this.simulator = simulator;
        this.modelPort = modelPort;
        this.taskBinder = taskBinder;
        this.executor = executor;
        this.verifier = verifier;
        this.properties = properties;
        this.sqlitePersistence = sqlitePersistence;
    }

    public RunRecord run(String requestId, String text) {
        RunRecord run = new RunRecord();
        run.setRunId(Ids.newId("base"));
        run.setRequestId(requestId == null ? Ids.newId("req") : requestId);
        run.setDeviceId(simulator.getDeviceId());
        run.setEnvironmentId(simulator.getEnvironmentId());
        run.setSessionId("baseline");
        run.setLifecycle(RunLifecycle.RUNNING);
        run.setPhase(RunPhase.COMPILE);
        run.getBudget().setDeadline(Instant.now().plusSeconds(properties.getBudget().getAbsoluteDeadlineSeconds()));
        run.getBudget().setMaxModelCalls(properties.getBudget().getMaxModelCalls());
        run.getBudget().setMaxToolCalls(properties.getBudget().getMaxToolCalls());
        run.getBudget().setMaxWriteActions(properties.getBudget().getMaxWriteActions());
        runStore.save(run);
        runStore.appendEvent(run, "RUN_RECEIVED", Ids.dict("text", text, "mode", "baseline", "model_mode", modelPort.mode()));

        StateSnapshot observe = executor.read(run, EnumSet.allOf(DeviceDomain.class));
        run.getBudget().countModel();
        CompiledTaskCandidate candidate = modelPort.compileTask(text, observe);
        runStore.appendEvent(run, "COMPILE", Ids.dict("routeHint", candidate.routeHint, "summary", candidate.summary));

        RouteType route = switch (candidate.routeHint == null ? "" : candidate.routeHint.toUpperCase()) {
            case "FAST" -> RouteType.FAST;
            case "AGENT", "MULTI_AGENT" -> RouteType.MULTI_AGENT;
            case "CHAT" -> RouteType.CHAT;
            case "REJECT" -> RouteType.REJECT;
            default -> RouteType.CLARIFY;
        };
        run.setRouteType(route);
        if (route == RouteType.REJECT) {
            finish(run, RunLifecycle.STOPPED, "UNSUPPORTED", candidate.rejectReason, GoalOutcome.UNSATISFIED);
            return run;
        }
        if (route == RouteType.CLARIFY) {
            run.setLifecycle(RunLifecycle.WAITING_CLARIFICATION);
            run.setResultSummary(candidate.clarifyQuestion);
            sqlitePersistence.persistRun(run);
            return run;
        }

        run.setTask(taskBinder.bind(run.getRunId(), text, properties.getDefaultsRuleId(), candidate));

        if (route == RouteType.FAST && candidate.fastAction != null) {
            String cap = String.valueOf(candidate.fastAction.get("capability_id"));
            @SuppressWarnings("unchecked")
            Map<String, Object> params = (Map<String, Object>) candidate.fastAction.get("params");
            ToolAction action = executor.executeWrite(run, cap, params);
            conclude(run, action);
            return run;
        }

        // docs/08 P2-2：基线 = 编译后一次性确定性展开，不再调用 planNext（避免混入逐步反馈）
        runStore.appendEvent(run, "BASELINE_PLAN", Ids.dict(
                "mode", "single_shot_deterministic_from_goals",
                "note", "不回传工具结果；非纯 FC，是编译目标的确定性展开"
        ));

        List<Map<String, Object>> steps = new ArrayList<>();
        StateSnapshot live = observe;
        for (Map<String, Object> goal : run.getTask().getGoals()) {
            String type = String.valueOf(goal.get("type"));
            boolean noCabin = run.getTask().getConstraints().stream().anyMatch(c -> "no_cabin_write".equals(c.get("type")));
            if ("cabin_temperature".equals(type) && !noCabin) {
                steps.add(Ids.dict("decision", "ACT", "capability_id", "cabin.set_temperature", "params", Ids.dict("value", goal.get("value"))));
            } else if ("cabin_fan".equals(type) && !noCabin) {
                steps.add(Ids.dict("decision", "ACT", "capability_id", "cabin.set_fan", "params", Ids.dict("value", goal.get("value"))));
            } else if ("media_volume".equals(type) && !Boolean.TRUE.equals(live.getState().get("media_muted"))) {
                steps.add(Ids.dict("decision", "ACT", "capability_id", "media.set_volume", "params", Ids.dict("value", goal.get("value"))));
            } else if ("nav_muted".equals(type)) {
                steps.add(Ids.dict("decision", "ACT", "capability_id", "navigation.set_muted", "params", Ids.dict("value", goal.get("value"))));
            } else if ("nav_prompt_enabled".equals(type)) {
                steps.add(Ids.dict("decision", "ACT", "capability_id", "navigation.set_prompt_enabled", "params", Ids.dict("value", goal.get("value"))));
            } else if ("nav_volume".equals(type)) {
                steps.add(Ids.dict("decision", "ACT", "capability_id", "navigation.set_volume", "params", Ids.dict("value", goal.get("value"))));
            }
        }

        List<Map<String, Object>> unique = new ArrayList<>();
        for (Map<String, Object> s : steps) {
            String cap = String.valueOf(s.get("capability_id"));
            boolean exists = unique.stream().anyMatch(u -> cap.equals(String.valueOf(u.get("capability_id"))));
            if (!exists) {
                unique.add(s);
            }
        }

        for (Map<String, Object> s : unique) {
            if (run.isCancelAccepted() || run.isTerminal()) break;
            String cap = String.valueOf(s.get("capability_id"));
            @SuppressWarnings("unchecked")
            Map<String, Object> params = (Map<String, Object>) s.get("params");
            ToolAction action = executor.executeWrite(run, cap, params);
            if (action.getExecutionStatus() == ExecutionStatus.UNKNOWN) {
                finish(run, RunLifecycle.STOPPED, "UNRESOLVED_ACTION", "未知动作", GoalOutcome.UNKNOWN);
                return run;
            }
        }

        if (run.getTask().getCriteria().stream().anyMatch(c -> "nav_prompt_event_played".equals(c.getTemplateId()))) {
            simulator.emitPromptEvent();
        }
        conclude(run, null);
        return run;
    }

    private void conclude(RunRecord run, ToolAction last) {
        Verifier.Result result = verifier.verifyTask(run);
        run.setGoalOutcome(result.outcome());
        run.getEvaluationSnapshot().put("details", result.details());
        if (result.outcome() == GoalOutcome.SATISFIED) {
            finish(run, RunLifecycle.COMPLETED, null, result.summary(), result.outcome());
        } else if (result.outcome() == GoalOutcome.UNKNOWN) {
            finish(run, RunLifecycle.STOPPED, "UNKNOWN_OUTCOME", result.summary(), result.outcome());
        } else {
            boolean any = result.details().stream().anyMatch(d -> "SATISFIED".equals(d.get("status")));
            finish(run, any ? RunLifecycle.PARTIAL : RunLifecycle.FAILED, any ? "PARTIAL" : "UNSATISFIED", result.summary(), result.outcome());
        }
    }

    private void finish(RunRecord run, RunLifecycle life, String stop, String summary, GoalOutcome outcome) {
        if (run.isTerminal()) return;
        run.setLifecycle(life);
        run.setPhase(RunPhase.FINISH);
        run.setStopReason(stop);
        run.setResultSummary(summary);
        run.setGoalOutcome(outcome);
        runStore.appendEvent(run, "RUN_FINISHED", Ids.dict("lifecycle", life.name(), "mode", "baseline"));
        sqlitePersistence.persistRun(run);
    }
}
