package com.deviceagent.model;

import com.deviceagent.capability.CapabilityRegistry;
import com.deviceagent.config.DeviceAgentProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ToolsForTaskTest {
    @Test
    void whitelistFollowsGoalsAndConstraints() {
        var props = new DeviceAgentProperties();
        var adapter = new OpenAiCompatibleModelAdapter(
                props,
                new ObjectMapper(),
                new ModelRouter(props),
                new CapabilityRegistry()
        );
        List<Map<String, Object>> tools = adapter.toolsForTask(
                List.of(Map.of("type", "cabin_temperature", "value", 23)),
                List.of(Map.of("type", "no_window"))
        );
        List<String> names = tools.stream().map(t -> {
            @SuppressWarnings("unchecked")
            Map<String, Object> fn = (Map<String, Object>) t.get("function");
            return String.valueOf(fn.get("name"));
        }).toList();
        assertTrue(names.contains("device_get_state"));
        assertTrue(names.contains("climate_set_temperature"));
        assertFalse(names.stream().anyMatch(n -> n.startsWith("window_")));
        assertFalse(names.contains("media_play"));
    }
}
