package com.deviceagent.model;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Normalize model JSON into harness contracts (params.value, criteria templates, route). */
public final class ModelOutputNormalizer {
    private ModelOutputNormalizer() {}

    public static void normalize(CompiledTaskCandidate c) {
        normalize(c, null);
    }

    public static void normalize(CompiledTaskCandidate c, String userText) {
        if (c == null) return;
        if (c.goals != null) {
            List<Map<String, Object>> goals = new ArrayList<>();
            for (Map<String, Object> g : c.goals) {
                goals.add(normalizeGoal(g));
            }
            c.goals = goals;
        }
        if (c.fastAction != null) {
            c.fastAction = normalizeAction(c.fastAction);
        }
        if (c.criteria == null) {
            c.criteria = new ArrayList<>();
        }
        if (c.criteria.isEmpty() && c.goals != null) {
            for (Map<String, Object> g : c.goals) {
                Map<String, Object> crit = criterionFromGoal(g);
                if (crit != null) c.criteria.add(crit);
            }
        } else {
            List<Map<String, Object>> crits = new ArrayList<>();
            for (Map<String, Object> raw : c.criteria) {
                crits.add(normalizeCriterion(raw));
            }
            c.criteria = crits;
        }
        if (c.constraints == null) {
            c.constraints = new ArrayList<>();
        }
        correctRoute(c, userText);
    }

    /**
     * Guard against models collapsing multi-goal / constrained cabin tasks into FAST.
     * Deterministic harness rule — does not invent goals, only forces AGENT when needed.
     */
    public static void correctRoute(CompiledTaskCandidate c, String userText) {
        if (c == null || !"FAST".equalsIgnoreCase(c.routeHint)) {
            return;
        }
        String text = userText == null ? "" : userText;
        if (looksComplexRequest(text)) {
            c.routeHint = "MULTI_AGENT";
            c.raw.put("route_corrected", "complex_request_force_multi_agent");
            return;
        }
        if (c.goals != null && c.goals.size() > 1) {
            c.routeHint = "MULTI_AGENT";
            c.raw.put("route_corrected", "multi_goal_force_multi_agent");
            return;
        }
        if (c.constraints != null && !c.constraints.isEmpty()) {
            c.routeHint = "MULTI_AGENT";
            c.raw.put("route_corrected", "constraints_force_multi_agent");
            return;
        }
        if (multiDomainGoals(c)) {
            c.routeHint = "MULTI_AGENT";
            c.raw.put("route_corrected", "multi_domain_force_multi_agent");
        }
    }

    public static boolean looksComplexRequest(String text) {
        if (text == null || text.isBlank()) return false;
        if (text.contains("休息") || text.contains("舒服")) return true;
        if (text.contains("不要开窗") || text.contains("不开窗")) return true;
        if (text.contains("保留导航") || text.contains("导航提示")) return true;
        if (text.contains("不要重启") || text.contains("不重启")) return true;
        if (text.contains("不调空调") || text.contains("空调先不要")) return true;
        if (text.contains("导航") && (text.contains("没有声音") || text.contains("无声") || text.contains("听不见"))) {
            return true;
        }
        boolean multiClause = text.contains("并且") || text.contains("同时") || text.contains("再")
                || text.contains("还要") || text.contains("然后") || text.contains("；");
        int hits = 0;
        if (text.contains("温度") || text.contains("空调")) hits++;
        if (text.contains("风量")) hits++;
        if (text.contains("车窗") || text.contains("开窗")) hits++;
        if (text.contains("媒体") || text.contains("音量") || text.contains("播放")) hits++;
        if (text.contains("导航")) hits++;
        return (multiClause && hits >= 2) || hits >= 3;
    }

    private static boolean multiDomainGoals(CompiledTaskCandidate c) {
        if (c.goals == null || c.goals.size() < 2) return false;
        boolean cabin = false, media = false, nav = false, window = false;
        for (Map<String, Object> g : c.goals) {
            String type = String.valueOf(g.get("type"));
            if (type.startsWith("cabin_") || "climate_power".equals(type)) cabin = true;
            else if (type.startsWith("media_")) media = true;
            else if (type.startsWith("nav_")) nav = true;
            else if ("window_position".equals(type)) window = true;
        }
        int domains = (cabin ? 1 : 0) + (media ? 1 : 0) + (nav ? 1 : 0) + (window ? 1 : 0);
        return domains >= 2;
    }

    public static Map<String, Object> normalizeAction(Map<String, Object> action) {
        Map<String, Object> out = new LinkedHashMap<>(action);
        Object cap = out.get("capability_id");
        if (cap == null) cap = out.get("capabilityId");
        String raw = String.valueOf(cap);
        String capId;
        // Already canonical domain.action — do not rewrite internal underscores in the action name.
        if (raw.contains(".")) {
            capId = raw;
        } else {
            capId = raw.replace('_', '.');
            if (raw.startsWith("climate_")) capId = "climate." + raw.substring("climate_".length());
            else if (raw.startsWith("cabin_")) capId = "climate." + raw.substring("cabin_".length());
            else if (raw.startsWith("media_")) capId = "media." + raw.substring("media_".length());
            else if (raw.startsWith("navigation_")) capId = "navigation." + raw.substring("navigation_".length());
            else if (raw.startsWith("window_")) capId = "window." + raw.substring("window_".length());
            else if (raw.startsWith("device_")) capId = "device." + raw.substring("device_".length());
        }
        out.put("capability_id", capId);
        Object paramsObj = out.get("params");
        Map<String, Object> params = new LinkedHashMap<>();
        if (paramsObj instanceof Map<?, ?> m) {
            m.forEach((k, v) -> params.put(String.valueOf(k), v));
        }
        if (!params.containsKey("value")
                && !capId.endsWith(".play")
                && !capId.endsWith(".pause")
                && !capId.endsWith(".start")
                && !capId.endsWith(".stop")
                && !capId.contains("window")) {
            for (String alias : List.of("temperature", "temp", "fan", "fan_level", "volume", "enabled", "muted", "power")) {
                if (params.containsKey(alias)) {
                    params.put("value", params.get(alias));
                    break;
                }
            }
        }
        if (capId.contains("window") && params.containsKey("position") && !params.containsKey("window")) {
            params.put("window", params.getOrDefault("id", "all"));
        }
        out.put("params", params);
        if (!out.containsKey("decision")) out.put("decision", "ACT");
        return out;
    }

    private static Map<String, Object> normalizeGoal(Map<String, Object> g) {
        Map<String, Object> out = new LinkedHashMap<>(g);
        String type = String.valueOf(out.getOrDefault("type", ""));
        type = switch (type) {
            case "temperature", "temp", "cabin_temp", "ac_temperature" -> "cabin_temperature";
            case "fan", "fan_level" -> "cabin_fan";
            case "power", "ac_power", "climate_on" -> "climate_power";
            case "volume", "media", "media_vol" -> "media_volume";
            case "play", "play_media" -> "media_play";
            case "pause" -> "media_pause";
            case "window", "window_open", "window_pos" -> "window_position";
            case "navigate", "navigation_start", "nav_destination" -> "nav_start";
            case "nav_prompt", "prompt_enabled" -> "nav_prompt_enabled";
            case "nav_mute", "navigation_muted" -> "nav_muted";
            case "nav_vol", "navigation_volume" -> "nav_volume";
            default -> type;
        };
        out.put("type", type);
        if (!out.containsKey("value")) {
            for (String alias : List.of("temperature", "temp", "fan", "volume", "enabled", "muted", "power")) {
                if (out.containsKey(alias)) {
                    out.put("value", out.get(alias));
                    break;
                }
            }
        }
        return out;
    }

    private static Map<String, Object> normalizeCriterion(Map<String, Object> raw) {
        Map<String, Object> out = new LinkedHashMap<>(raw);
        if (!out.containsKey("template_id") && out.containsKey("templateId")) {
            out.put("template_id", out.get("templateId"));
        }
        Object paramsObj = out.get("params");
        Map<String, Object> params = new LinkedHashMap<>();
        if (paramsObj instanceof Map<?, ?> m) {
            m.forEach((k, v) -> params.put(String.valueOf(k), v));
        }
        if (!params.containsKey("value")) {
            for (String alias : List.of("temperature", "temp", "fan", "volume", "enabled", "muted")) {
                if (params.containsKey(alias)) {
                    params.put("value", params.get(alias));
                    break;
                }
            }
        }
        out.put("params", params);
        return out;
    }

    private static Map<String, Object> criterionFromGoal(Map<String, Object> goal) {
        String type = String.valueOf(goal.get("type"));
        Object value = goal.get("value");
        String template = switch (type) {
            case "cabin_temperature" -> "cabin_temperature_eq";
            case "cabin_fan" -> "cabin_fan_eq";
            case "media_volume" -> "media_volume_eq";
            case "nav_prompt_enabled" -> "nav_prompt_enabled_eq";
            case "nav_muted" -> "nav_muted_eq";
            case "nav_volume" -> "nav_volume_eq";
            default -> null;
        };
        if (template == null) return null;
        Map<String, Object> c = new LinkedHashMap<>();
        c.put("template_id", template);
        c.put("params", Map.of("value", value));
        c.put("required", true);
        c.put("source", String.valueOf(goal.getOrDefault("source", "model")));
        return c;
    }
}
