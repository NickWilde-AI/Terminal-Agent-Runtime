package com.deviceagent;

import com.deviceagent.capability.CapabilityRegistry;
import com.deviceagent.harness.GoalCompiler;
import com.deviceagent.model.CompiledTaskCandidate;
import com.deviceagent.simulator.DeviceSimulator;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class NavigationCapabilityTest {

    @Test
    void registryExposesNavAndLifeCapabilities() {
        var registry = new CapabilityRegistry();
        assertTrue(registry.get("navigation.start").isPresent());
        assertTrue(registry.get("navigation.add_waypoint").isPresent());
        assertTrue(registry.get("navigation.query_eta").isPresent());
        assertTrue(registry.get("navigation.navigate_home").isPresent());
        assertTrue(registry.get("life.search_shops").isPresent());
        assertTrue(registry.get("life.close").isPresent());
        assertEquals("navigation.start", registry.canonical("navigation.set_route"));
        assertEquals("capabilities-v3", CapabilityRegistry.VERSION);
    }

    @Test
    void setRouteOpensAndUnknownPoiFailsHonestly() {
        var sim = new DeviceSimulator();
        var ok = sim.applyWrite("a1", "k1", "navigation.start", Map.of("destination", "东方明珠"),
                sim.getEnvironmentId(), null, Map.of());
        assertEquals("APPLIED", ok.status);
        assertEquals(true, sim.readState(null).getState().get("navigation_active"));
        assertEquals("东方明珠", sim.readState(null).getState().get("navigation_destination"));

        var bad = sim.applyWrite("a2", "k2", "navigation.start", Map.of("destination", "火星基地999"),
                sim.getEnvironmentId(), null, Map.of());
        assertEquals("NOT_APPLIED", bad.status);
        assertEquals("SEARCH_NO_CANDIDATE", bad.message);
    }

    @Test
    void waypointKeepsDestination() {
        var sim = new DeviceSimulator();
        sim.applyWrite("a1", "k1", "navigation.start", Map.of("destination", "虹桥机场"),
                sim.getEnvironmentId(), null, Map.of());
        var wp = sim.applyWrite("a2", "k2", "navigation.add_waypoint", Map.of("name", "星巴克"),
                sim.getEnvironmentId(), null, Map.of());
        assertEquals("APPLIED", wp.status);
        var state = sim.readState(null).getState();
        assertEquals("虹桥机场", state.get("navigation_destination"));
        assertTrue(((List<?>) state.get("navigation_waypoints")).contains("星巴克"));
    }

    @Test
    void addWaypointWithoutDestinationFails() {
        var sim = new DeviceSimulator();
        // default active but destination null
        var wp = sim.applyWrite("a1", "k1", "navigation.add_waypoint", Map.of("name", "星巴克"),
                sim.getEnvironmentId(), null, Map.of());
        assertEquals("NOT_APPLIED", wp.status);
        assertEquals("NO_ACTIVE_DESTINATION", wp.message);
    }

    @Test
    void goHomeAndCompany() {
        var sim = new DeviceSimulator();
        sim.applyWrite("a1", "k1", "navigation.navigate_home", Map.of(),
                sim.getEnvironmentId(), null, Map.of());
        assertEquals("虹桥幸福里", sim.readState(null).getState().get("navigation_destination"));
        sim.applyWrite("a2", "k2", "navigation.navigate_company", Map.of(),
                sim.getEnvironmentId(), null, Map.of());
        assertEquals("陆家嘴办公楼", sim.readState(null).getState().get("navigation_destination"));
    }

    @Test
    void lifeStubsOnlyFlipSessionFlags() {
        var sim = new DeviceSimulator();
        var search = sim.applyWrite("a1", "k1", "life.search_shops", Map.of("keyword", "咖啡"),
                sim.getEnvironmentId(), null, Map.of());
        assertEquals("APPLIED", search.status);
        assertEquals(true, sim.readState(null).getState().get("life_session_active"));
        assertEquals("shop_list", sim.readState(null).getState().get("life_phase"));
        sim.applyWrite("a2", "k2", "life.close", Map.of(), sim.getEnvironmentId(), null, Map.of());
        assertEquals(false, sim.readState(null).getState().get("life_session_active"));
    }

    @Test
    void compilerDirectOpenAndMultiPointHome() {
        CompiledTaskCandidate go = GoalCompiler.compile("去东方明珠", null, List.of());
        assertEquals("FAST", go.routeHint);
        assertEquals("navigation.start", go.fastAction.get("capability_id"));

        CompiledTaskCandidate multi = GoalCompiler.compile("回家途经加油站", null, List.of());
        assertEquals("MULTI_AGENT", multi.routeHint);
        assertTrue(multi.goals.stream().anyMatch(g -> "nav_home".equals(g.get("type"))));
        assertTrue(multi.goals.stream().anyMatch(g -> "nav_add_waypoint".equals(g.get("type"))
                && "加油站".equals(g.get("name"))));
    }

    @Test
    void compilerClarifyWaypointWithoutDestination() {
        var snap = new com.deviceagent.domain.StateSnapshot();
        java.util.Map<String, Object> state = new java.util.LinkedHashMap<>();
        state.put("navigation_active", true);
        state.put("navigation_destination", null);
        snap.setState(state);
        CompiledTaskCandidate c = GoalCompiler.compile("加个途经点星巴克", snap, List.of());
        assertEquals("CLARIFY", c.routeHint);
    }

    @Test
    void checkoutIsLifeNotNavigation() {
        CompiledTaskCandidate c = GoalCompiler.compile("去结算", null, List.of());
        assertEquals("FAST", c.routeHint);
        assertEquals("life.go_to_checkout", c.fastAction.get("capability_id"));
        assertFalse(c.goals.stream().anyMatch(g -> "nav_start".equals(g.get("type"))));
    }

    @Test
    void explicitFoodOrderEntersLifeSession() {
        CompiledTaskCandidate c = GoalCompiler.compile("点外卖咖啡", null, List.of());
        assertEquals("FAST", c.routeHint);
        assertEquals("life.search_shops", c.fastAction.get("capability_id"));
        assertEquals("咖啡", ((Map<?, ?>) c.fastAction.get("params")).get("keyword"));
    }

    @Test
    void roadsideCoffeePrefersNavWaypointNotLife() {
        var snap = new com.deviceagent.domain.StateSnapshot();
        java.util.Map<String, Object> state = new java.util.LinkedHashMap<>();
        state.put("navigation_active", true);
        state.put("navigation_destination", "东方明珠");
        snap.setState(state);
        CompiledTaskCandidate c = GoalCompiler.compile("顺路咖啡", snap, List.of());
        assertEquals("FAST", c.routeHint);
        assertEquals("navigation.add_waypoint", c.fastAction.get("capability_id"));
        assertFalse(c.goals.stream().anyMatch(g -> String.valueOf(g.get("type")).startsWith("life_")));
    }

    @Test
    void navigationStartInterruptsLifeSession() {
        var sim = new DeviceSimulator();
        sim.applyWrite("a1", "k1", "life.search_shops", Map.of("keyword", "咖啡"),
                sim.getEnvironmentId(), null, Map.of());
        assertEquals(true, sim.readState(null).getState().get("life_session_active"));
        sim.applyWrite("a2", "k2", "navigation.start", Map.of("destination", "东方明珠"),
                sim.getEnvironmentId(), null, Map.of());
        var state = sim.readState(null).getState();
        assertEquals(true, state.get("navigation_active"));
        assertEquals(false, state.get("life_session_active"));
        assertEquals("idle", state.get("life_phase"));
    }
}
