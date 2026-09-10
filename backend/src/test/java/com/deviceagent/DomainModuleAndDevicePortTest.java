package com.deviceagent;

import com.deviceagent.capability.CapabilityRegistry;
import com.deviceagent.capability.DomainModule;
import com.deviceagent.capability.IotDomainModule;
import com.deviceagent.capability.TerminalDomainModule;
import com.deviceagent.device.ActionRecord;
import com.deviceagent.device.DevicePort;
import com.deviceagent.device.FaultType;
import com.deviceagent.domain.DeviceDomain;
import com.deviceagent.domain.StateSnapshot;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.*;

class DomainModuleAndDevicePortTest {

    @Test
    void registryLoadsTerminalAndIotModules() {
        CapabilityRegistry registry = new CapabilityRegistry(
                List.of(new TerminalDomainModule(), new IotDomainModule()));
        assertEquals(List.of("terminal", "iot"), registry.moduleIds());
        assertTrue(registry.get("navigation.start").isPresent());
        assertTrue(registry.get("iot.light.set_power").isPresent());
    }

    @Test
    void customDomainModuleCanRegisterWithoutTouchingHarness() {
        DomainModule custom = new DomainModule() {
            @Override
            public String id() {
                return "custom";
            }

            @Override
            public void register(com.deviceagent.capability.CapabilityRegistrar registrar) {
                registrar.add("custom.ping", "自定义域样例", true, "IOT",
                        Map.of("value", com.deviceagent.capability.Schema.bool()));
            }
        };
        CapabilityRegistry registry = new CapabilityRegistry(List.of(custom));
        assertEquals(List.of("custom"), registry.moduleIds());
        assertTrue(registry.get("custom.ping").isPresent());
        assertTrue(registry.validate("custom.ping", Map.of("value", true)).ok());
    }

    @Test
    void stubDevicePortIsUsableWithoutSimulatorTypes() {
        DevicePort port = new InMemoryLightPort();
        ActionRecord rec = port.applyWrite("a1", "k1", "iot.light.set_power", Map.of("value", true),
                port.getEnvironmentId(), Instant.now().plusSeconds(5), Map.of(), "run", 1);
        assertEquals("APPLIED", rec.status);
        assertEquals(true, port.snapshot().getState().get("light_power"));
        port.injectFault(FaultType.REJECT, "iot.light.set_power", 1);
        ActionRecord denied = port.applyWrite("a2", "k2", "iot.light.set_power", Map.of("value", false),
                port.getEnvironmentId(), Instant.now().plusSeconds(5), Map.of(), "run", 1);
        assertEquals("NOT_APPLIED", denied.status);
    }

    /** Minimal second DevicePort implementation — no Simulator types leaked. */
    static final class InMemoryLightPort implements DevicePort {
        private final Map<String, Object> state = new LinkedHashMap<>(Map.of("light_power", false));
        private final Map<String, ActionRecord> actions = new LinkedHashMap<>();
        private String env = "env-light";
        private FaultType fault = FaultType.NONE;
        private int remaining;

        @Override
        public String getDeviceId() {
            return "terminal-light-stub";
        }

        @Override
        public String getEnvironmentId() {
            return env;
        }

        @Override
        public StateSnapshot readState(Set<DeviceDomain> domains) {
            return snapshot();
        }

        @Override
        public StateSnapshot snapshot() {
            StateSnapshot s = new StateSnapshot();
            s.setDeviceId(getDeviceId());
            s.setEnvironmentId(env);
            s.setObservedAt(Instant.now());
            s.setState(new LinkedHashMap<>(state));
            s.setDomainRevisions(Map.of("IOT", 1L));
            s.setRevision(1);
            s.setOrigins(Map.of());
            return s;
        }

        @Override
        public Map<String, Object> view() {
            return Map.of("state", snapshot().getState());
        }

        @Override
        public ActionRecord applyWrite(String actionId, String idempotencyKey, String capabilityId,
                                      Map<String, Object> params, String environmentId, Instant deadline,
                                      Map<String, Long> expectedRevisions, String runId, int goalVersion) {
            ActionRecord a = new ActionRecord();
            a.actionId = actionId;
            a.idempotencyKey = idempotencyKey;
            a.capabilityId = capabilityId;
            a.params = new LinkedHashMap<>(params);
            a.environmentId = environmentId;
            a.runId = runId;
            a.goalVersion = goalVersion;
            a.createdAt = Instant.now();
            if (fault == FaultType.REJECT && remaining > 0) {
                remaining--;
                a.status = "NOT_APPLIED";
                a.message = "DEVICE_REJECTED";
                a.finishedAt = Instant.now();
                actions.put(actionId, a);
                return a;
            }
            if ("iot.light.set_power".equals(capabilityId)) {
                state.put("light_power", params.get("value"));
            }
            a.status = "APPLIED";
            a.message = "OK";
            a.finishedAt = Instant.now();
            actions.put(actionId, a);
            return a;
        }

        @Override
        public ActionRecord queryAction(String actionId) {
            return actions.get(actionId);
        }

        @Override
        public void resetToDefaults() {
            state.put("light_power", false);
        }

        @Override
        public void forceNewEnvironment() {
            env = "env-" + System.nanoTime();
        }

        @Override
        public void injectFault(FaultType type, String capabilityId, int times) {
            fault = type;
            remaining = times;
        }

        @Override
        public void clearFault() {
            fault = FaultType.NONE;
            remaining = 0;
        }

        @Override
        public void applyInitialState(Map<String, Object> fields) {
            state.putAll(fields);
        }

        @Override
        public void externalChange(String field, Object value) {
            state.put(field, value);
        }

        @Override
        public void addChangeListener(Consumer<Map<String, Object>> listener) {
        }

        @Override
        public void onPersist(Consumer<Map<String, Object>> sink) {
        }
    }
}
