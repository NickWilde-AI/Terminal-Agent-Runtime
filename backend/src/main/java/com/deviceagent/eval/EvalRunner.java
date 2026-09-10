package com.deviceagent.eval;

import com.deviceagent.capability.CapabilityRegistry;
import com.deviceagent.config.DeviceAgentProperties;
import com.deviceagent.domain.ExecutionStatus;
import com.deviceagent.domain.Ids;
import com.deviceagent.domain.RunLifecycle;
import com.deviceagent.domain.RunRecord;
import com.deviceagent.harness.BaselineRunner;
import com.deviceagent.harness.HarnessService;
import com.deviceagent.model.ModelPort;
import com.deviceagent.policy.PolicyEngine;
import com.deviceagent.device.FaultType;
import com.deviceagent.simulator.DeviceSimulator;
import com.deviceagent.store.InMemoryRunStore;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
public class EvalRunner {
    private final HarnessService harnessService;
    private final DeviceSimulator simulator;
    private final InMemoryRunStore runStore;
    private final PolicyEngine policyEngine;
    private final CapabilityRegistry capabilityRegistry;
    private final ObjectMapper objectMapper;
    private final ModelPort modelPort;
    private final BaselineRunner baselineRunner;
    private final DeviceAgentProperties properties;
    private volatile Map<String, Object> lastReport;

    public EvalRunner(
            HarnessService harnessService,
            DeviceSimulator simulator,
            InMemoryRunStore runStore,
            PolicyEngine policyEngine,
            CapabilityRegistry capabilityRegistry,
            ObjectMapper objectMapper,
            ModelPort modelPort,
            BaselineRunner baselineRunner,
            DeviceAgentProperties properties
    ) {
        this.harnessService = harnessService;
        this.simulator = simulator;
        this.runStore = runStore;
        this.policyEngine = policyEngine;
        this.capabilityRegistry = capabilityRegistry;
        this.objectMapper = objectMapper;
        this.modelPort = modelPort;
        this.baselineRunner = baselineRunner;
        this.properties = properties;
    }

    public Map<String, Object> lastReport() {
        return lastReport;
    }

    public synchronized Map<String, Object> run(String mode) {
        List<EvalCase> cases = EvalCatalog.all();
        List<Map<String, Object>> results = new ArrayList<>();
        int passed = 0;
        int falseSuccess = 0;

        for (EvalCase c : cases) {
            Map<String, Object> one = runOne(c, mode);
            results.add(one);
            if (Boolean.TRUE.equals(one.get("passed"))) {
                passed++;
            }
            if (Boolean.TRUE.equals(one.get("false_success"))) {
                falseSuccess++;
            }
        }

        Map<String, Object> report = new LinkedHashMap<>();
        report.put("mode", mode);
        report.put("dataset_version", "eval-seeds-v1");
        report.put("model_mode", modelPort.mode());
        report.put("total", cases.size());
        report.put("passed", passed);
        report.put("failed", cases.size() - passed);
        report.put("correct_handling_rate", cases.isEmpty() ? 0.0 : (double) passed / cases.size());
        report.put("false_success", falseSuccess);
        report.put("cases", results);
        report.put("generated_at", Instant.now().toString());
        report.put("note", "agent=状态反馈循环；baseline=单次计划后执行且不回传工具结果。Fake 与真实 API 报告分开，不可混算");
        lastReport = report;
        try {
            Path dir = Path.of("reports");
            Files.createDirectories(dir);
            Path file = dir.resolve("eval-" + mode + "-" + System.currentTimeMillis() + ".json");
            Files.writeString(file, objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(report));
            report.put("report_path", file.toString());
            Files.writeString(dir.resolve("last-" + mode + ".json"),
                    objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(report));
        } catch (Exception ignored) {
        }
        return report;
    }

    private Map<String, Object> runOne(EvalCase c, String mode) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", c.id);
        out.put("category", c.category);
        out.put("completable", c.completable);
        try {
            // clear active blockers（含取消接受，避免上一例暂停线程继续跑）
            harnessService.releaseEvalPause();
            for (RunRecord r : runStore.list()) {
                r.setUnresolvedUnknown(false);
                if (!r.isTerminal()) {
                    r.setCancelAccepted(true);
                    r.setLifecycle(RunLifecycle.CANCELLED);
                }
            }
            harnessService.awaitIdle(3_000);
            simulator.forceNewEnvironment();
            try {
                simulator.resetToDefaults();
            } catch (RuntimeException ex) {
                simulator.forceNewEnvironment();
                simulator.resetToDefaults();
            }
            if (c.initialState != null) {
                simulator.applyInitialState(c.initialState);
            }
            if (c.faultType != null) {
                simulator.injectFault(FaultType.valueOf(c.faultType), c.faultCapability, c.faultTimes);
            }

            if ("policy".equals(c.category) && c.candidateCapability != null) {
                return runPolicyCase(c, out);
            }

            boolean oldConfirm = properties != null && properties.isRequireConfirmation();
            if (c.requireConfirmation) {
                properties.setRequireConfirmation(true);
            }
            boolean needsMidRun = !"baseline".equals(mode)
                    && (c.interveneText != null || c.externalAfterCompile != null || c.cancel);
            try {
                RunRecord run;
                if ("baseline".equals(mode)) {
                    run = baselineRunner.run("eval-" + c.id + "-" + UUID.randomUUID(), c.request);
                } else {
                    if (needsMidRun) {
                        harnessService.armEvalPauseAfterGoalBound();
                    }
                    // 运行中介入/外部扰动/取消：异步启动，GOAL_BOUND 屏障后再脚本化
                    run = harnessService.createRun(
                            "eval-" + c.id + "-" + UUID.randomUUID(),
                            c.request,
                            "eval",
                            !needsMidRun
                    );
                }

                if (needsMidRun) {
                    waitUntil(run, r -> r.isTerminal()
                                    || r.getLifecycle() == RunLifecycle.WAITING_CLARIFICATION
                                    || r.getLifecycle() == RunLifecycle.WAITING_CONFIRMATION
                                    || hasEvent(r, "GOAL_BOUND")
                                    || hasEvent(r, "EVAL_PAUSE"),
                            8_000);
                    run = runStore.find(run.getRunId()).orElse(run);
                }

                // scripted interventions — 暂停窗口内改目标，再 resume 由原执行线程继续（避免双 runAgent）
                if (c.clarifyAnswer != null && run.getLifecycle() == RunLifecycle.WAITING_CLARIFICATION) {
                    if (needsMidRun) {
                        harnessService.releaseEvalPause();
                    }
                    run = harnessService.answerClarification(run.getRunId(), c.clarifyAnswer);
                    if (needsMidRun && (c.interveneText != null || c.externalAfterCompile != null || c.cancel)) {
                        harnessService.armEvalPauseAfterGoalBound();
                        waitUntil(run, r -> r.isTerminal()
                                        || r.getLifecycle() == RunLifecycle.WAITING_CONFIRMATION
                                        || hasEvent(r, "GOAL_BOUND")
                                        || hasEvent(r, "EVAL_PAUSE"),
                                8_000);
                        run = runStore.find(run.getRunId()).orElse(run);
                    }
                }
                if (c.externalAfterCompile != null && !run.isTerminal()) {
                    c.externalAfterCompile.forEach(simulator::externalChange);
                }
                if (c.interveneText != null && !run.isTerminal()) {
                    // 暂停窗口内只改目标，不另起 runAgent；release 后由原线程执行
                    run = harnessService.intervene(
                            run.getRunId(), "CHANGE_GOAL", c.interveneText, run.getTask().getGoalVersion(), false);
                }
                if (needsMidRun) {
                    harnessService.releaseEvalPause();
                }
                if (c.requireConfirmation && c.confirmDecision != null) {
                    waitUntil(run, r -> r.isTerminal()
                                    || (r.getLifecycle() == RunLifecycle.WAITING_CONFIRMATION && r.getPending() != null),
                            8_000);
                    run = runStore.find(run.getRunId()).orElse(run);
                    if (run.getLifecycle() == RunLifecycle.WAITING_CONFIRMATION && run.getPending() != null) {
                        run = harnessService.answerPending(
                                run.getRunId(),
                                run.getPending().getPendingId(),
                                run.getPending().getGoalVersion(),
                                c.confirmDecision,
                                null
                        );
                    }
                }
                if (c.forceClarifyTimeout && run.getLifecycle() == RunLifecycle.WAITING_CLARIFICATION) {
                    run.getBudget().setDeadline(java.time.Instant.now().minusSeconds(1));
                    waitUntil(run, RunRecord::isTerminal, 3_000);
                    run = runStore.find(run.getRunId()).orElse(run);
                }
                if (c.cancel && !run.isTerminal()) {
                    run = harnessService.cancel(run.getRunId());
                }

                if (needsMidRun) {
                    waitUntil(run, RunRecord::isTerminal, 12_000);
                    run = runStore.find(run.getRunId()).orElse(run);
                }

                // 断言前清故障，避免 READ_FAIL 污染终态读（docs F05）
                simulator.clearFault();

                out.put("lifecycle", run.getLifecycle().name());
                out.put("route", run.getRouteType() == null ? null : run.getRouteType().name());
                out.put("goal_outcome", run.getGoalOutcome() == null ? null : run.getGoalOutcome().name());
                out.put("stop_reason", run.getStopReason());

                List<String> errors = new ArrayList<>();
                if (c.allowedLifecycles != null && !c.allowedLifecycles.contains(run.getLifecycle().name())) {
                    errors.add("lifecycle=" + run.getLifecycle());
                }
                if (c.expectedRoute != null && (run.getRouteType() == null || !c.expectedRoute.equals(run.getRouteType().name()))) {
                    errors.add("route=" + run.getRouteType());
                }
                Map<String, Object> state = simulator.readState(null).getState();
                if (c.finalStateEquals != null) {
                    for (var e : c.finalStateEquals.entrySet()) {
                        if (!eq(state.get(e.getKey()), e.getValue())) {
                            errors.add("state." + e.getKey() + "=" + state.get(e.getKey()) + " expected " + e.getValue());
                        }
                    }
                }
                if (c.forbidCapabilities != null) {
                    for (String cap : c.forbidCapabilities) {
                        boolean wrote = run.getActions().stream().anyMatch(a ->
                                cap.equals(a.getCapabilityId())
                                        && a.getExecutionStatus() != ExecutionStatus.BLOCKED
                                        && a.getExecutionStatus() != ExecutionStatus.SKIPPED
                                        && a.getExecutionStatus() != ExecutionStatus.PREPARED);
                        if (wrote) errors.add("forbidden capability dispatched: " + cap);
                    }
                }
                if (c.requireNoWrites && run.getActions().stream().anyMatch(a -> a.getExecutionStatus() == ExecutionStatus.APPLIED)) {
                    errors.add("expected no APPLIED writes");
                }
                if (c.requireAppliedCapability != null) {
                    String want = capabilityRegistry.canonical(c.requireAppliedCapability);
                    boolean ok = run.getActions().stream().anyMatch(a ->
                            want.equals(capabilityRegistry.canonical(a.getCapabilityId()))
                                    && a.getExecutionStatus() == ExecutionStatus.APPLIED);
                    if (!ok) errors.add("missing APPLIED " + c.requireAppliedCapability);
                }
                // false success: COMPLETED but required state not met
                if (run.getLifecycle() == RunLifecycle.COMPLETED && c.finalStateEquals != null) {
                    for (var e : c.finalStateEquals.entrySet()) {
                        if (!eq(state.get(e.getKey()), e.getValue())) {
                            falseSuccessMark(out);
                            errors.add("false success on " + e.getKey());
                        }
                    }
                }

                boolean pass = errors.isEmpty();
                out.put("passed", pass);
                out.put("message", pass ? "ok" : String.join("; ", errors));
                out.put("details", Ids.dict("state", state, "actions", run.getActions().size(), "exec_mode", mode));
                return out;
            } finally {
                // 任何异常/早退都必须释放屏障，否则下一例会在 GOAL_BOUND 挂死
                harnessService.releaseEvalPause();
                if (c.requireConfirmation) {
                    properties.setRequireConfirmation(oldConfirm);
                }
            }
        } catch (Exception ex) {
            out.put("passed", false);
            out.put("message", ex.getMessage());
            return out;
        }
    }

    private Map<String, Object> runPolicyCase(EvalCase c, Map<String, Object> out) {
        RunRecord stub = new RunRecord();
        stub.setRunId("policy");
        stub.setDeviceId(simulator.getDeviceId());
        stub.getTask().setConstraints(c.constraints == null ? List.of() : c.constraints);
        var decision = policyEngine.decide(stub, c.candidateCapability, c.candidateParams);
        boolean denied = "DENY".equals(decision.decision().name()) || !capabilityRegistry.get(c.candidateCapability).isPresent();
        if (c.candidateCapability != null && capabilityRegistry.validate(c.candidateCapability, c.candidateParams).ok() == false) {
            denied = true;
        }
        boolean pass = c.expectDeny == denied;
        out.put("passed", pass);
        out.put("lifecycle", "N/A");
        out.put("message", pass ? "ok" : "policy decision=" + decision.decision());
        return out;
    }

    private void falseSuccessMark(Map<String, Object> out) {
        out.put("false_success", true);
    }

    private static boolean eq(Object a, Object b) {
        if (a instanceof Number n1 && b instanceof Number n2) return n1.intValue() == n2.intValue();
        return String.valueOf(a).equals(String.valueOf(b));
    }

    private static boolean hasEvent(RunRecord run, String type) {
        return run.getEvents().stream().anyMatch(e -> type.equals(e.getType()));
    }

    private void waitUntil(RunRecord run, java.util.function.Predicate<RunRecord> pred, long timeoutMs) {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (System.currentTimeMillis() < deadline) {
            RunRecord latest = runStore.find(run.getRunId()).orElse(run);
            if (pred.test(latest)) {
                return;
            }
            try {
                Thread.sleep(20);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }
}
