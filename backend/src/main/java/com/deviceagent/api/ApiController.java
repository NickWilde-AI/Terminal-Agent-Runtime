package com.deviceagent.api;

import com.deviceagent.capability.CapabilityRegistry;
import com.deviceagent.config.DeviceAgentProperties;
import com.deviceagent.domain.Ids;
import com.deviceagent.eval.EvalRunner;
import com.deviceagent.harness.HarnessService;
import com.deviceagent.memory.MemoryEntry;
import com.deviceagent.memory.MemoryService;
import com.deviceagent.model.ModelPort;
import com.deviceagent.model.ModelRouter;
import com.deviceagent.simulator.DeviceSimulator;
import com.deviceagent.store.InMemoryRunStore;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1")
public class ApiController {
    private final HarnessService harnessService;
    private final InMemoryRunStore runStore;
    private final DeviceSimulator simulator;
    private final CapabilityRegistry capabilityRegistry;
    private final EvalRunner evalRunner;
    private final ModelPort modelPort;
    private final DeviceAgentProperties properties;
    private final MemoryService memoryService;
    private final ModelRouter modelRouter;
    private final SseHub sseHub;

    public ApiController(
            HarnessService harnessService,
            InMemoryRunStore runStore,
            DeviceSimulator simulator,
            CapabilityRegistry capabilityRegistry,
            EvalRunner evalRunner,
            ModelPort modelPort,
            DeviceAgentProperties properties,
            MemoryService memoryService,
            ModelRouter modelRouter,
            SseHub sseHub
    ) {
        this.harnessService = harnessService;
        this.runStore = runStore;
        this.simulator = simulator;
        this.capabilityRegistry = capabilityRegistry;
        this.evalRunner = evalRunner;
        this.modelPort = modelPort;
        this.properties = properties;
        this.memoryService = memoryService;
        this.modelRouter = modelRouter;
        this.sseHub = sseHub;
    }

    @PostMapping("/runs")
    public Map<String, Object> createRun(@RequestBody CreateRunRequest req) {
        try {
            // 异步执行：立即返回 run_id，便于模型等待期间取消（docs I01/I02）
            var run = harnessService.createRun(req.requestId(), req.text(), req.sessionId(), false);
            return harnessService.toView(run);
        } catch (IllegalStateException ex) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, ex.getMessage());
        } catch (Exception ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, ex.getMessage());
        }
    }

    @GetMapping("/runs")
    public Map<String, Object> listRuns() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("runs", harnessService.listRuns().stream().map(harnessService::toView).toList());
        return out;
    }

    @GetMapping("/runs/{runId}")
    public Map<String, Object> getRun(@PathVariable String runId) {
        var run = runStore.find(runId).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return harnessService.toView(run);
    }

    @GetMapping("/runs/{runId}/events")
    public Map<String, Object> events(@PathVariable String runId, @RequestParam(defaultValue = "0") long afterSeq) {
        runStore.find(runId).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        var events = runStore.eventsAfter(runId, afterSeq);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("run_id", runId);
        out.put("events", events);
        out.put("latest_seq", events.isEmpty() ? afterSeq : events.get(events.size() - 1).getSeq());
        return out;
    }

    @GetMapping(value = "/runs/{runId}/events/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamEvents(
            @PathVariable String runId,
            @RequestParam(defaultValue = "0") long afterSeq
    ) {
        runStore.find(runId).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return sseHub.subscribeRun(runId, afterSeq);
    }

    @GetMapping(value = "/device/state/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamDevice() {
        return sseHub.subscribeDevice();
    }

    @GetMapping("/runs/{runId}/replay")
    public Map<String, Object> replay(@PathVariable String runId) {
        try {
            return harnessService.replay(runId);
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, ex.getMessage());
        }
    }

    @PostMapping("/runs/{runId}/cancel")
    public Map<String, Object> cancel(@PathVariable String runId) {
        return harnessService.toView(harnessService.cancel(runId));
    }

    @PostMapping("/runs/{runId}/clarify")
    public Map<String, Object> clarify(@PathVariable String runId, @RequestBody ClarifyRequest req) {
        try {
            return harnessService.toView(harnessService.answerClarification(runId, req.answer()));
        } catch (IllegalStateException ex) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, ex.getMessage());
        }
    }

    @PostMapping("/runs/{runId}/intervene")
    public Map<String, Object> intervene(@PathVariable String runId, @RequestBody InterveneRequest req) {
        try {
            return harnessService.toView(harnessService.intervene(runId, req.type(), req.text(), req.expectedGoalVersion()));
        } catch (IllegalStateException ex) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, ex.getMessage());
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, ex.getMessage());
        }
    }

    @PostMapping("/runs/{runId}/answer")
    public Map<String, Object> answer(@PathVariable String runId, @RequestBody AnswerRequest req) {
        try {
            return harnessService.toView(harnessService.answerPending(
                    runId, req.pendingId(), req.goalVersion(), req.decision(), req.answer()));
        } catch (IllegalStateException ex) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, ex.getMessage());
        }
    }

    @GetMapping("/capabilities")
    public List<Map<String, Object>> capabilities() {
        return capabilityRegistry.all().stream().map(c -> c.toMap()).toList();
    }

    @GetMapping("/device/state")
    public Map<String, Object> deviceState() {
        var snap = simulator.readState(null);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("device_id", snap.getDeviceId());
        out.put("environment_id", snap.getEnvironmentId());
        out.put("observed_at", snap.getObservedAt());
        out.put("domain_revisions", snap.getDomainRevisions());
        out.put("state", snap.getState());
        out.put("simulation", true);
        out.put("note", "本地设备模拟器状态（联调/回归）");
        return out;
    }

    @PostMapping("/experiment/reset")
    public Map<String, Object> reset() {
        return harnessService.resetExperiment();
    }

    @PostMapping("/experiment/force-new-environment")
    public Map<String, Object> forceEnv() {
        simulator.forceNewEnvironment();
        return deviceState();
    }

    @PostMapping("/experiment/fault")
    public Map<String, Object> fault(@RequestBody FaultRequest req) {
        simulator.injectFault(
                DeviceSimulator.FaultType.valueOf(req.type()),
                req.capabilityId(),
                req.times() == null ? 1 : req.times()
        );
        return Ids.dict("ok", true, "type", req.type(), "capability_id", req.capabilityId(), "times", req.times());
    }

    @PostMapping("/experiment/external-change")
    public Map<String, Object> external(@RequestBody ExternalChangeRequest req) {
        simulator.externalChange(req.field(), req.value());
        return deviceState();
    }

    @PostMapping("/evals/run")
    public Map<String, Object> runEval(@RequestParam(defaultValue = "agent") String mode) {
        return evalRunner.run(mode);
    }

    @GetMapping("/evals/last")
    public Map<String, Object> lastEval() {
        Map<String, Object> last = evalRunner.lastReport();
        if (last == null) {
            return Ids.dict("available", false, "note", "尚未评测");
        }
        return last;
    }

    @PostMapping("/experiment/require-confirmation")
    public Map<String, Object> requireConfirmation(@RequestBody Map<String, Object> body) {
        boolean enabled = Boolean.TRUE.equals(body.get("enabled")) || "true".equalsIgnoreCase(String.valueOf(body.get("enabled")));
        properties.setRequireConfirmation(enabled);
        return Ids.dict("ok", true, "require_confirmation", properties.isRequireConfirmation());
    }

    @GetMapping("/meta")
    public Map<String, Object> meta() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("product", "Terminal Agent Runtime");
        m.put("product_zh", "智能终端 Agent Runtime");
        m.put("phase", "v1");
        m.put("defaults_rule_id", "demo-defaults-v1");
        m.put("local_simulator", true);
        m.put("model_mode", modelPort.mode());
        m.put("model_id", modelRouter.activeModelId());
        m.put("model_placement", modelRouter.placement());
        m.put("model_base_url", properties.getModel().getBaseUrl());
        m.put("model_api_configured", properties.getModel().getApiKey() != null && !properties.getModel().getApiKey().isBlank());
        m.put("require_confirmation", properties.isRequireConfirmation());
        m.put("persistence", properties.getPersistence());
        m.put("memory_enabled", true);
        m.put("sse_enabled", true);
        m.put("multi_agent", true);
        m.put("agent_roles", List.of("MAIN", "PLANNER", "REVIEWER"));
        m.put("disclaimer", "智能终端 Agent Runtime；本地默认设备模拟器联调，模型为阶跃 Step（OpenAI-compatible），端云共用 ModelPort。复杂任务走主 Agent / 规划 / 审核三角色，写设备仍只经 Runtime。");
        return m;
    }

    @GetMapping("/memory")
    public Map<String, Object> listMemory(@RequestParam(defaultValue = "web") String sessionId) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("session_id", sessionId);
        out.put("memories", memoryService.list(sessionId).stream().map(MemoryEntry::toMap).toList());
        out.put("note", "长期记忆只影响默认值建议，不越过 Policy");
        return out;
    }

    @PostMapping("/memory")
    public Map<String, Object> writeMemory(@RequestBody MemoryWriteRequest req) {
        if (req.utterance() != null && !req.utterance().isBlank()) {
            return memoryService.tryWriteFromUtterance(
                    req.utterance(),
                    req.sessionId() == null ? "web" : req.sessionId(),
                    req.sourceRunId()
            );
        }
        MemoryEntry e = new MemoryEntry();
        e.setSessionId(req.sessionId() == null ? "web" : req.sessionId());
        e.setCategory(req.category() == null ? "preference" : req.category());
        e.setKey(req.key());
        e.setValue(req.value());
        e.setDomain(req.domain() == null ? "general" : req.domain());
        e.setSourceRunId(req.sourceRunId());
        e.setConfidence(req.confidence() == null ? 0.9 : req.confidence());
        e.setNote("api_manual");
        return memoryService.writeManual(e);
    }

    @DeleteMapping("/memory/{id}")
    public Map<String, Object> deleteMemory(@PathVariable String id) {
        boolean ok = memoryService.delete(id);
        if (!ok) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "memory not found");
        }
        return Ids.dict("ok", true, "id", id);
    }

    @PostMapping("/model/placement")
    public Map<String, Object> setPlacement(@RequestBody Map<String, Object> body) {
        String placement = String.valueOf(body.getOrDefault("placement", "cloud"));
        if (!"cloud".equalsIgnoreCase(placement) && !"edge".equalsIgnoreCase(placement)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "placement must be cloud|edge");
        }
        modelRouter.setPlacement(placement);
        return Ids.dict(
                "ok", true,
                "placement", modelRouter.placement(),
                "model_id", modelRouter.activeModelId(),
                "note", "端侧为演进占位，非车规 NPU 部署"
        );
    }

    public record CreateRunRequest(@NotBlank String text, String requestId, String sessionId) {}
    public record ClarifyRequest(@NotBlank String answer) {}
    public record FaultRequest(@NotBlank String type, String capabilityId, Integer times) {}
    public record ExternalChangeRequest(@NotBlank String field, Object value) {}
    public record InterveneRequest(@NotBlank String type, String text, Integer expectedGoalVersion) {}
    public record AnswerRequest(@NotBlank String pendingId, int goalVersion, @NotBlank String decision, String answer) {}
    public record MemoryWriteRequest(
            String utterance,
            String sessionId,
            String sourceRunId,
            String category,
            String key,
            String value,
            String domain,
            Double confidence
    ) {}
}
