package com.deviceagent.model;

import com.deviceagent.domain.StateSnapshot;
import com.deviceagent.harness.GoalCompiler;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Deterministic fake model for local demos and tests. Not mixed into real API scores.
 * Delegates compile to {@link GoalCompiler}; planNext covers all registered write capabilities.
 */
@Component
@ConditionalOnProperty(prefix = "device-agent.model", name = "mode", havingValue = "fake", matchIfMissing = true)
public class FakeModelAdapter implements ModelPort {

    @Override
    public String mode() {
        return "fake";
    }

    @Override
    public CompiledTaskCandidate compileTask(
            String userText,
            StateSnapshot observation,
            List<Map<String, Object>> memoryHints
    ) {
        CompiledTaskCandidate c = GoalCompiler.compile(userText, observation, memoryHints);
        c.raw.put("model_mode", "fake");
        ModelOutputNormalizer.normalize(c, userText);
        return c;
    }

    @Override
    public Map<String, Object> planNext(
            String runId,
            List<Map<String, Object>> goals,
            List<Map<String, Object>> constraints,
            List<Map<String, Object>> criteria,
            StateSnapshot observation,
            List<Map<String, Object>> priorActions,
            List<Map<String, Object>> memoryHints
    ) {
        Map<String, Object> state = observation.getState();
        boolean noCabin = constraints.stream().anyMatch(c -> "no_cabin_write".equals(c.get("type")));
        boolean noWindow = constraints.stream().anyMatch(c -> "no_window".equals(c.get("type")));
        boolean noMedia = constraints.stream().anyMatch(c -> "no_media_write".equals(c.get("type")));

        for (Map<String, Object> goal : goals) {
            String type = String.valueOf(goal.get("type"));
            if ("climate_power".equals(type) && !noCabin) {
                boolean target = Boolean.TRUE.equals(goal.get("value"));
                boolean cur = Boolean.TRUE.equals(state.get("climate_power"));
                if (cur != target) {
                    return action("climate.set_power", Map.of("value", target), "空调电源未满足");
                }
            }
            if ("cabin_temperature".equals(type) && !noCabin) {
                int target = ((Number) goal.get("value")).intValue();
                int cur = ((Number) state.getOrDefault("temperature_setpoint", 26)).intValue();
                if (cur != target) {
                    return action("climate.set_temperature", Map.of("value", target), "温度未满足");
                }
            }
            if ("cabin_fan".equals(type) && !noCabin) {
                int target = ((Number) goal.get("value")).intValue();
                int cur = ((Number) state.getOrDefault("fan_level", 3)).intValue();
                if (cur != target) {
                    return action("climate.set_fan", Map.of("value", target), "风量未满足");
                }
            }
            if ("window_position".equals(type) && !noWindow) {
                String window = String.valueOf(goal.getOrDefault("window", "all"));
                int position = ((Number) goal.get("position")).intValue();
                if (!windowsMatch(state, window, position)) {
                    return action("window.set_position",
                            Map.of("window", window, "position", position), "车窗未满足");
                }
            }
            if ("media_play".equals(type) && !noMedia) {
                String artist = String.valueOf(goal.get("artist"));
                boolean playing = Boolean.TRUE.equals(state.get("media_playing"));
                String cur = String.valueOf(state.getOrDefault("media_artist", ""));
                if (!playing || !artist.equals(cur)) {
                    return action("media.play", Map.of("artist", artist), "媒体未播放");
                }
            }
            if ("media_pause".equals(type) && !noMedia) {
                if (Boolean.TRUE.equals(state.get("media_playing"))) {
                    return action("media.pause", Map.of(), "媒体未暂停");
                }
            }
            if ("media_volume".equals(type) && !noMedia) {
                boolean muted = Boolean.TRUE.equals(state.get("media_muted"));
                if (muted) continue;
                int target = ((Number) goal.get("value")).intValue();
                int cur = ((Number) state.getOrDefault("media_volume", 8)).intValue();
                if (cur != target) {
                    return action("media.set_volume", Map.of("value", target), "媒体音量未满足");
                }
            }
            if ("nav_start".equals(type)) {
                String dest = String.valueOf(goal.get("destination"));
                boolean active = Boolean.TRUE.equals(state.get("navigation_active"));
                String cur = String.valueOf(state.getOrDefault("navigation_destination", ""));
                if (!active || !dest.equals(cur)) {
                    return action("navigation.start", Map.of("destination", dest), "导航未启动");
                }
            }
            if ("nav_stop".equals(type)) {
                if (Boolean.TRUE.equals(state.get("navigation_active"))) {
                    return action("navigation.stop", Map.of(), "导航未停止");
                }
            }
            if ("nav_prompt_enabled".equals(type)) {
                boolean target = Boolean.TRUE.equals(goal.get("value"));
                boolean cur = Boolean.TRUE.equals(state.get("prompt_enabled"));
                if (cur != target) {
                    return action("navigation.set_prompt_enabled", Map.of("value", target), "播报开关未满足");
                }
            }
            if ("nav_muted".equals(type)) {
                boolean target = Boolean.TRUE.equals(goal.get("value"));
                boolean cur = Boolean.TRUE.equals(state.get("navigation_muted"));
                if (cur != target) {
                    return action("navigation.set_muted", Map.of("value", target), "导航静音未满足");
                }
            }
            if ("nav_volume".equals(type)) {
                int target = ((Number) goal.get("value")).intValue();
                int cur = ((Number) state.getOrDefault("navigation_volume", 5)).intValue();
                if (cur != target) {
                    return action("navigation.set_volume", Map.of("value", target), "导航音量未满足");
                }
            }
        }
        if (!Boolean.TRUE.equals(state.get("route_available")) || !Boolean.TRUE.equals(state.get("focus_available"))) {
            boolean navDiag = goals.stream().anyMatch(g -> String.valueOf(g.get("type")).startsWith("nav_"));
            if (navDiag) {
                return Map.of("decision", "FINISH", "reason", "音频路由或焦点不可用，无法继续低风险修复，已停止并解释");
            }
        }
        return Map.of("decision", "FINISH", "reason", "观察显示目标已满足或无需动作");
    }

    private static boolean windowsMatch(Map<String, Object> state, String window, int position) {
        if ("all".equals(window)) {
            for (String w : List.of("front_left", "front_right", "rear_left", "rear_right")) {
                int cur = ((Number) state.getOrDefault("window_" + w, 0)).intValue();
                if (cur != position) return false;
            }
            return true;
        }
        int cur = ((Number) state.getOrDefault("window_" + window, 0)).intValue();
        return cur == position;
    }

    private static Map<String, Object> action(String capabilityId, Map<String, Object> params, String reason) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("decision", "ACT");
        m.put("capability_id", capabilityId);
        m.put("params", params);
        m.put("reason", reason);
        return m;
    }
}
