package com.deviceagent.model;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ModelOutputNormalizerTest {

    @Test
    void remapsTemperatureParamAlias() {
        Map<String, Object> action = new LinkedHashMap<>();
        action.put("capability_id", "cabin.set_temperature");
        action.put("params", Map.of("temperature", 23));
        Map<String, Object> out = ModelOutputNormalizer.normalizeAction(action);
        assertEquals(23, ((Map<?, ?>) out.get("params")).get("value"));
    }

    @Test
    void forcesAgentOnRestRequestEvenIfModelSaysFast() {
        CompiledTaskCandidate c = new CompiledTaskCandidate();
        c.routeHint = "FAST";
        c.fastAction = Map.of("capability_id", "cabin.set_temperature", "params", Map.of("value", 23));
        c.goals = new ArrayList<>(List.of(Map.of("type", "cabin_temperature", "value", 23)));
        ModelOutputNormalizer.normalize(c, "休息一下，调舒服点，不要开窗，保留导航提示");
        assertEquals("AGENT", c.routeHint);
        assertEquals("complex_request_force_agent", c.raw.get("route_corrected"));
    }

    @Test
    void forcesAgentOnMultiGoal() {
        CompiledTaskCandidate c = new CompiledTaskCandidate();
        c.routeHint = "FAST";
        c.goals = new ArrayList<>(List.of(
                Map.of("type", "cabin_temperature", "value", 23),
                Map.of("type", "cabin_fan", "value", 1)
        ));
        ModelOutputNormalizer.normalize(c, "设温度和风量");
        assertEquals("AGENT", c.routeHint);
        assertTrue(c.criteria.size() >= 2);
    }

    @Test
    void keepsFastForSimpleSet() {
        CompiledTaskCandidate c = new CompiledTaskCandidate();
        c.routeHint = "FAST";
        c.goals = new ArrayList<>(List.of(Map.of("type", "cabin_temperature", "value", 23)));
        ModelOutputNormalizer.normalize(c, "把空调设为 23 度");
        assertEquals("FAST", c.routeHint);
    }
}
