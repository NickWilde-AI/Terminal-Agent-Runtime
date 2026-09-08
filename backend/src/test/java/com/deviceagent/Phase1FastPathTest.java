package com.deviceagent;

import com.deviceagent.harness.HarnessService;
import com.deviceagent.simulator.DeviceSimulator;
import com.deviceagent.store.InMemoryRunStore;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class Phase1FastPathTest {

    @Autowired HarnessService harnessService;
    @Autowired DeviceSimulator simulator;
    @Autowired InMemoryRunStore runStore;

    @BeforeEach
    void reset() {
        simulator.forceNewEnvironment();
        simulator.resetToDefaults();
        // Clear unresolved flags by forcing new env; runs remain in memory but terminal.
        for (var run : runStore.list()) {
            run.setUnresolvedUnknown(false);
            if (!run.isTerminal()) {
                run.setLifecycle(com.deviceagent.domain.RunLifecycle.CANCELLED);
            }
        }
    }

    @Test
    void q01_setTemperature23() {
        simulator.externalChange("temperature_setpoint", 26);
        var run = harnessService.createRun("req-" + UUID.randomUUID(), "把空调设为 23 度", "test");
        assertEquals("FAST", run.getRouteType() == null ? null : run.getRouteType().name(),
                () -> "stop=" + run.getStopReason() + " summary=" + run.getResultSummary()
                        + " events=" + run.getEvents().stream().map(e -> e.getType()).toList());
        assertEquals("COMPLETED", run.getLifecycle().name(),
                () -> "stop=" + run.getStopReason() + " summary=" + run.getResultSummary()
                        + " outcome=" + run.getGoalOutcome()
                        + " actions=" + run.getActions()
                        + " eval=" + run.getEvaluationSnapshot());
        assertEquals(23, simulator.readState(null).getState().get("temperature_setpoint"));
        assertTrue(run.getActions().stream().anyMatch(a ->
                ("cabin.set_temperature".equals(a.getCapabilityId()) || "climate.set_temperature".equals(a.getCapabilityId()))
                        && a.getExecutionStatus().name().equals("APPLIED")));
        assertNotNull(run.getResultSummary());
        assertFalse(run.getResultSummary().contains("全部完成") && run.getActions().isEmpty());
    }

    @Test
    void q02_already23_noWrite() {
        simulator.externalChange("temperature_setpoint", 23);
        var run = harnessService.createRun("req-" + UUID.randomUUID(), "把空调设为 23 度", "test");
        assertEquals("FAST", run.getRouteType().name());
        assertEquals("COMPLETED", run.getLifecycle().name());
        assertTrue(run.getActions().isEmpty() || run.getActions().stream().noneMatch(a ->
                a.getExecutionStatus().name().equals("APPLIED")));
        assertTrue(run.getResultSummary().contains("已是") || run.getResultSummary().contains("无需")
                || run.getResultSummary().contains("当前设定"));
        assertEquals(23, simulator.readState(null).getState().get("temperature_setpoint"));
    }

    @Test
    void ackNotApplied_noFalseSuccess() {
        simulator.externalChange("temperature_setpoint", 26);
        simulator.injectFault(DeviceSimulator.FaultType.ACK_NOT_APPLIED, "cabin.set_temperature", 1);
        var run = harnessService.createRun("req-" + UUID.randomUUID(), "把空调设为 23 度", "test");
        assertEquals(26, simulator.readState(null).getState().get("temperature_setpoint"));
        assertTrue(run.getActions().stream().anyMatch(a -> a.getExecutionStatus().name().equals("NOT_APPLIED")));
        assertFalse("COMPLETED".equals(run.getLifecycle().name())
                && "SATISFIED".equals(run.getGoalOutcome() == null ? null : run.getGoalOutcome().name()));
    }

    @Test
    void openFrontLeftWindowHalf() {
        var run = harnessService.createRun("req-" + UUID.randomUUID(), "打开左前车窗一半", "test");
        assertEquals("FAST", run.getRouteType().name());
        assertEquals("COMPLETED", run.getLifecycle().name());
        assertEquals(50, simulator.readState(null).getState().get("window_front_left"));
        assertEquals(0, simulator.readState(null).getState().get("window_front_right"));
    }

    @Test
    void complexRestUsesAgent() {
        var run = harnessService.createRun("req-" + UUID.randomUUID(),
                "后排要休息，把座舱调整舒服一点；媒体声音调低，但保留导航提示，不要开窗。", "test");
        assertEquals("AGENT", run.getRouteType().name());
        assertTrue(run.getLifecycle().name().equals("COMPLETED") || run.getLifecycle().name().equals("PARTIAL"));
        Map<String, Object> state = simulator.readState(null).getState();
        assertEquals(23, state.get("temperature_setpoint"));
        assertEquals(1, state.get("fan_level"));
        assertEquals(6, state.get("media_volume"));
        assertEquals(false, state.get("window_open"));
    }
}
