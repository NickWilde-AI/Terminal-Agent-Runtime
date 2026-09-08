package com.deviceagent.api;

import com.deviceagent.domain.RunLifecycle;
import com.deviceagent.domain.RuntimeEvent;
import com.deviceagent.harness.HarnessService;
import com.deviceagent.simulator.DeviceSimulator;
import com.deviceagent.store.InMemoryRunStore;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

/**
 * SSE fan-out for run events and device state. Keeps HTTP long-poll off the workbench.
 */
@Component
public class SseHub {
    private static final Set<RunLifecycle> TERMINAL = Set.of(
            RunLifecycle.COMPLETED, RunLifecycle.FAILED, RunLifecycle.STOPPED,
            RunLifecycle.CANCELLED, RunLifecycle.TIMED_OUT, RunLifecycle.INTERRUPTED,
            RunLifecycle.PARTIAL
    );

    private final InMemoryRunStore store;
    private final DeviceSimulator simulator;
    private final HarnessService harnessService;
    private final ScheduledExecutorService heartbeats =
            Executors.newSingleThreadScheduledExecutor(r -> {
                Thread t = new Thread(r, "sse-heartbeat");
                t.setDaemon(true);
                return t;
            });

    private final ConcurrentHashMap<String, CopyOnWriteArrayList<SseEmitter>> runEmitters = new ConcurrentHashMap<>();
    private final CopyOnWriteArrayList<SseEmitter> deviceEmitters = new CopyOnWriteArrayList<>();

    public SseHub(InMemoryRunStore store, DeviceSimulator simulator, HarnessService harnessService) {
        this.store = store;
        this.simulator = simulator;
        this.harnessService = harnessService;
    }

    @PostConstruct
    void wire() {
        store.addEventListener(this::onRuntimeEvent);
        simulator.addChangeListener(this::onDeviceChange);
        heartbeats.scheduleAtFixedRate(this::pingAll, 15, 15, TimeUnit.SECONDS);
    }

    @PreDestroy
    void shutdown() {
        heartbeats.shutdownNow();
        runEmitters.values().forEach(list -> list.forEach(SseEmitter::complete));
        deviceEmitters.forEach(SseEmitter::complete);
    }

    public SseEmitter subscribeRun(String runId, long afterSeq) {
        var run = store.find(runId).orElseThrow(() -> new IllegalArgumentException("run not found"));
        SseEmitter emitter = new SseEmitter(0L);
        runEmitters.computeIfAbsent(runId, id -> new CopyOnWriteArrayList<>()).add(emitter);
        Consumer<SseEmitter> cleanup = e -> {
            var list = runEmitters.get(runId);
            if (list != null) {
                list.remove(e);
                if (list.isEmpty()) {
                    runEmitters.remove(runId, list);
                }
            }
        };
        emitter.onCompletion(() -> cleanup.accept(emitter));
        emitter.onTimeout(() -> cleanup.accept(emitter));
        emitter.onError(ex -> cleanup.accept(emitter));

        try {
            for (RuntimeEvent event : store.eventsAfter(runId, afterSeq)) {
                send(emitter, "event", eventPayload(event));
            }
            send(emitter, "run", harnessService.toView(run));
            send(emitter, "device", devicePayload());
            if (TERMINAL.contains(run.getLifecycle())) {
                emitter.complete();
            }
        } catch (Exception ex) {
            emitter.completeWithError(ex);
        }
        return emitter;
    }

    public SseEmitter subscribeDevice() {
        SseEmitter emitter = new SseEmitter(0L);
        deviceEmitters.add(emitter);
        emitter.onCompletion(() -> deviceEmitters.remove(emitter));
        emitter.onTimeout(() -> deviceEmitters.remove(emitter));
        emitter.onError(ex -> deviceEmitters.remove(emitter));
        try {
            send(emitter, "device", devicePayload());
        } catch (Exception ex) {
            emitter.completeWithError(ex);
        }
        return emitter;
    }

    private void onRuntimeEvent(RuntimeEvent event) {
        var list = runEmitters.get(event.getRunId());
        if (list == null || list.isEmpty()) {
            return;
        }
        Map<String, Object> payload = eventPayload(event);
        Map<String, Object> runView = store.find(event.getRunId())
                .map(harnessService::toView)
                .orElse(null);
        Map<String, Object> device = devicePayload();
        for (SseEmitter emitter : List.copyOf(list)) {
            try {
                send(emitter, "event", payload);
                if (runView != null) {
                    send(emitter, "run", runView);
                }
                send(emitter, "device", device);
                if (runView != null && isTerminalLifecycle(runView.get("lifecycle"))) {
                    emitter.complete();
                }
            } catch (Exception ex) {
                emitter.completeWithError(ex);
            }
        }
    }

    private void onDeviceChange(Map<String, Object> view) {
        Map<String, Object> payload = normalizeDevice(view);
        for (SseEmitter emitter : List.copyOf(deviceEmitters)) {
            try {
                send(emitter, "device", payload);
            } catch (Exception ex) {
                emitter.completeWithError(ex);
            }
        }
        // Also refresh open run streams so workbench state stays live without client poll.
        for (var entry : runEmitters.entrySet()) {
            for (SseEmitter emitter : List.copyOf(entry.getValue())) {
                try {
                    send(emitter, "device", payload);
                } catch (Exception ex) {
                    emitter.completeWithError(ex);
                }
            }
        }
    }

    private void pingAll() {
        for (var entry : runEmitters.entrySet()) {
            for (SseEmitter emitter : List.copyOf(entry.getValue())) {
                try {
                    send(emitter, "ping", Map.of("ts", System.currentTimeMillis()));
                } catch (Exception ex) {
                    emitter.completeWithError(ex);
                }
            }
        }
        for (SseEmitter emitter : List.copyOf(deviceEmitters)) {
            try {
                send(emitter, "ping", Map.of("ts", System.currentTimeMillis()));
            } catch (Exception ex) {
                emitter.completeWithError(ex);
            }
        }
    }

    private Map<String, Object> devicePayload() {
        return normalizeDevice(simulator.view());
    }

    private Map<String, Object> normalizeDevice(Map<String, Object> view) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("device_id", view.getOrDefault("device_id", simulator.getDeviceId()));
        out.put("environment_id", view.get("environment_id"));
        out.put("observed_at", view.get("observed_at"));
        out.put("domain_revisions", view.get("domain_revisions"));
        out.put("state", view.get("state"));
        out.put("simulation", true);
        out.put("note", "本地设备模拟器状态（SSE）");
        return out;
    }

    private Map<String, Object> eventPayload(RuntimeEvent e) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("seq", e.getSeq());
        out.put("type", e.getType());
        out.put("at", e.getAt());
        out.put("goalVersion", e.getGoalVersion());
        out.put("actionId", e.getActionId());
        out.put("payload", e.getPayload());
        out.put("runId", e.getRunId());
        return out;
    }

    private boolean isTerminalLifecycle(Object life) {
        if (life == null) {
            return false;
        }
        try {
            return TERMINAL.contains(RunLifecycle.valueOf(String.valueOf(life)));
        } catch (Exception ex) {
            return false;
        }
    }

    private void send(SseEmitter emitter, String name, Object data) throws IOException {
        emitter.send(SseEmitter.event().name(name).data(data, MediaType.APPLICATION_JSON));
    }
}
