package com.deviceagent.agent;

import com.deviceagent.domain.DeviceTask;
import com.deviceagent.domain.ReviewDecision;
import com.deviceagent.domain.StateSnapshot;
import com.deviceagent.harness.TaskBinder;
import com.deviceagent.model.ModelOutputNormalizer;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Deterministic helpers shared by Fake planner/reviewer and harness wiring. */
public final class MultiAgentSupport {
    private MultiAgentSupport() {}

    public static TaskSpec taskSpecFrom(DeviceTask task, String runId, String modelId) {
        TaskSpec spec = new TaskSpec();
        spec.runId = runId;
        spec.modelId = modelId;
        spec.goalVersion = task.getGoalVersion();
        spec.goal = String.valueOf(task.getBindingContext().getOrDefault("summary", task.getRawText()));
        spec.goals = new ArrayList<>(task.getGoals());
        spec.constraints = new ArrayList<>(task.getConstraints());
        for (var c : task.getCriteria()) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("template_id", c.getTemplateId());
            row.put("params", c.getParams());
            row.put("required", c.isRequired());
            spec.successCriteria.add(row);
        }
        for (var g : task.getGoals()) {
            Map<String, Object> action = TaskBinder.actionFor(g);
            if (action != null) {
                spec.allowedCapabilities.add(String.valueOf(action.get("capability_id")));
            }
        }
        spec.allowedCapabilities = new ArrayList<>(spec.allowedCapabilities.stream().distinct().toList());
        return spec;
    }

    private static boolean aliasMatch(String a, String b) {
        if (a == null || b == null) return false;
        if (a.equals(b)) return true;
        return a.replace("cabin.", "climate.").equals(b.replace("cabin.", "climate."));
    }

    private static boolean goalCoversCapability(List<Map<String, Object>> goals, String cap) {
        if (goals == null) return false;
        for (Map<String, Object> g : goals) {
            Map<String, Object> action = TaskBinder.actionFor(g);
            if (action != null && aliasMatch(String.valueOf(action.get("capability_id")), cap)) return true;
        }
        return false;
    }

    /**
     * Build a full candidate plan covering unmet goals (Fake / baseline planner).
     * Does not execute — only proposes actions.
     */
    public static PlanDraft buildPlanDraft(
            TaskSpec spec,
            StateSnapshot observation,
            List<Map<String, Object>> priorActions,
            int revisionRound,
            String modelId
    ) {
        PlanDraft draft = new PlanDraft();
        draft.runId = spec.runId;
        draft.goalVersion = spec.goalVersion;
        draft.modelId = modelId;
        draft.revisionRound = revisionRound;
        Map<String, Object> state = observation == null ? Map.of() : observation.getState();
        boolean noCabin = hasConstraint(spec.constraints, "no_cabin_write");
        boolean noWindow = hasConstraint(spec.constraints, "no_window");
        boolean noMedia = hasConstraint(spec.constraints, "no_media_write");

        int idx = 0;
        for (Map<String, Object> goal : spec.goals) {
            String type = String.valueOf(goal.get("type"));
            Map<String, Object> action = null;
            if ("climate_power".equals(type) && !noCabin) {
                boolean target = Boolean.TRUE.equals(goal.get("value"));
                if (!Objects.equals(Boolean.TRUE.equals(state.get("climate_power")), target)) {
                    action = act("climate.set_power", Map.of("value", target), "空调电源");
                } else {
                    draft.assumptions.add(type + " already satisfied");
                }
            } else if ("cabin_temperature".equals(type) && !noCabin) {
                int target = ((Number) goal.get("value")).intValue();
                int cur = ((Number) state.getOrDefault("temperature_setpoint", 26)).intValue();
                if (cur != target) action = act("climate.set_temperature", Map.of("value", target), "温度");
                else draft.assumptions.add(type + " already satisfied");
            } else if ("cabin_fan".equals(type) && !noCabin) {
                int target = ((Number) goal.get("value")).intValue();
                int cur = ((Number) state.getOrDefault("fan_level", 3)).intValue();
                if (cur != target) action = act("climate.set_fan", Map.of("value", target), "风量");
                else draft.assumptions.add(type + " already satisfied");
            } else if ("window_position".equals(type) && !noWindow) {
                String window = String.valueOf(goal.getOrDefault("window", "all"));
                int position = ((Number) goal.get("position")).intValue();
                action = act("window.set_position", Map.of("window", window, "position", position), "车窗");
            } else if ("media_play".equals(type) && !noMedia) {
                String artist = String.valueOf(goal.get("artist"));
                boolean playing = Boolean.TRUE.equals(state.get("media_playing"));
                String cur = String.valueOf(state.getOrDefault("media_artist", ""));
                if (!playing || !artist.equals(cur)) {
                    action = act("media.play", Map.of("artist", artist), "媒体播放");
                } else draft.assumptions.add(type + " already satisfied");
            } else if ("media_pause".equals(type) && !noMedia) {
                if (Boolean.TRUE.equals(state.get("media_playing"))) {
                    action = act("media.pause", Map.of(), "媒体暂停");
                } else draft.assumptions.add(type + " already satisfied");
            } else if ("media_volume".equals(type) && !noMedia) {
                if (!Boolean.TRUE.equals(state.get("media_muted"))) {
                    int target = ((Number) goal.get("value")).intValue();
                    int cur = ((Number) state.getOrDefault("media_volume", 8)).intValue();
                    if (cur != target) action = act("media.set_volume", Map.of("value", target), "媒体音量");
                    else draft.assumptions.add(type + " already satisfied");
                } else {
                    draft.assumptions.add("media muted — skip volume write");
                }
            } else if ("nav_start".equals(type)) {
                String dest = String.valueOf(goal.get("destination"));
                boolean active = Boolean.TRUE.equals(state.get("navigation_active"));
                String cur = String.valueOf(state.getOrDefault("navigation_destination", ""));
                if (!active || !dest.equals(cur)) {
                    action = act("navigation.start", Map.of("destination", dest), "导航启动");
                } else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_stop".equals(type)) {
                if (Boolean.TRUE.equals(state.get("navigation_active"))) {
                    action = act("navigation.stop", Map.of(), "导航停止");
                } else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_home".equals(type)) {
                Object home = state.get("navigation_home");
                boolean active = Boolean.TRUE.equals(state.get("navigation_active"));
                if (!active || !Objects.equals(home, state.get("navigation_destination"))) {
                    action = act("navigation.navigate_home", Map.of(), "导航回家");
                } else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_company".equals(type)) {
                Object company = state.get("navigation_company");
                boolean active = Boolean.TRUE.equals(state.get("navigation_active"));
                if (!active || !Objects.equals(company, state.get("navigation_destination"))) {
                    action = act("navigation.navigate_company", Map.of(), "导航去公司");
                } else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_add_waypoint".equals(type)) {
                String name = String.valueOf(goal.get("name"));
                Object wp = state.get("navigation_waypoints");
                boolean has = wp instanceof List<?> list && list.contains(name);
                if (!has) action = act("navigation.add_waypoint", Map.of("name", name), "追加途经点");
                else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_remove_waypoint".equals(type)) {
                String name = String.valueOf(goal.get("name"));
                Object wp = state.get("navigation_waypoints");
                boolean has = wp instanceof List<?> list && list.contains(name);
                if (has) action = act("navigation.remove_waypoint", Map.of("name", name), "删除途经点");
                else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_preference".equals(type)) {
                String pref = String.valueOf(goal.get("value"));
                if (!pref.equals(String.valueOf(state.getOrDefault("navigation_preference", "")))) {
                    action = act("navigation.set_preference", Map.of("value", pref), "路线偏好");
                } else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_pause".equals(type)) {
                if (!Boolean.TRUE.equals(state.get("navigation_paused"))) {
                    action = act("navigation.pause", Map.of(), "暂停导航");
                } else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_resume".equals(type)) {
                if (Boolean.TRUE.equals(state.get("navigation_paused"))) {
                    action = act("navigation.resume", Map.of(), "继续导航");
                } else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_query_eta".equals(type)) {
                action = act("navigation.query_eta", Map.of(), "查询ETA");
            } else if ("nav_query_status".equals(type)) {
                action = act("navigation.query_status", Map.of(), "查询导航状态");
            } else if ("nav_query_waypoints".equals(type)) {
                action = act("navigation.query_waypoints", Map.of(), "查询途经点");
            } else if ("nav_prompt_enabled".equals(type)) {
                boolean target = Boolean.TRUE.equals(goal.get("value"));
                if (!Objects.equals(Boolean.TRUE.equals(state.get("prompt_enabled")), target)) {
                    action = act("navigation.set_prompt_enabled", Map.of("value", target), "导航播报");
                } else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_muted".equals(type)) {
                boolean target = Boolean.TRUE.equals(goal.get("value"));
                if (!Objects.equals(Boolean.TRUE.equals(state.get("navigation_muted")), target)) {
                    action = act("navigation.set_muted", Map.of("value", target), "导航静音");
                } else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_volume".equals(type)) {
                int target = ((Number) goal.get("value")).intValue();
                int cur = ((Number) state.getOrDefault("navigation_volume", 5)).intValue();
                if (cur != target) action = act("navigation.set_volume", Map.of("value", target), "导航音量");
                else draft.assumptions.add(type + " already satisfied");
            } else if ("nav_diagnostic".equals(type) || "media_keep_muted".equals(type)) {
                draft.assumptions.add("观察类目标：" + type + "，不产生写动作");
            }
            if (action != null) {
                action = ModelOutputNormalizer.normalizeAction(action);
                draft.actions.add(action);
                draft.order.add(idx++);
                draft.expectedEffects.add(Map.of(
                        "capability_id", action.get("capability_id"),
                        "params", action.get("params")
                ));
            }
        }
        if (draft.actions.isEmpty()) {
            draft.assumptions.add("观察显示目标已满足或无需写动作");
        }
        if (priorActions != null && !priorActions.isEmpty()) {
            draft.preconditions.add(Map.of("prior_actions", priorActions.size()));
        }
        return draft;
    }

    /** Deterministic semantic review used by Fake and as OpenAI parse fallback. */
    public static ReviewResult review(TaskSpec spec, PlanDraft draft, String modelId) {
        ReviewResult result = new ReviewResult();
        result.runId = spec.runId;
        result.goalVersion = spec.goalVersion;
        result.modelId = modelId;

        boolean noCabin = hasConstraint(spec.constraints, "no_cabin_write");
        boolean noWindow = hasConstraint(spec.constraints, "no_window");
        boolean noMedia = hasConstraint(spec.constraints, "no_media_write");

        for (Map<String, Object> action : draft.actions) {
            String cap = String.valueOf(action.get("capability_id"));
            if (noCabin && cap.startsWith("climate.")) {
                result.violatedConstraints.add("no_cabin_write vs " + cap);
            }
            if (noWindow && cap.startsWith("window.")) {
                result.violatedConstraints.add("no_window vs " + cap);
            }
            if (noMedia && cap.startsWith("media.")) {
                result.violatedConstraints.add("no_media_write vs " + cap);
            }
            if (!spec.allowedCapabilities.isEmpty()
                    && spec.allowedCapabilities.stream().noneMatch(a -> a.equals(cap) || aliasMatch(a, cap))
                    && !"device.get_state".equals(cap) && !"device.read_state".equals(cap)
                    && !goalCoversCapability(spec.goals, cap)) {
                result.riskyActions.add("capability not in allowed set: " + cap);
            }
        }

        for (Map<String, Object> goal : spec.goals) {
            String type = String.valueOf(goal.get("type"));
            if ("nav_diagnostic".equals(type) || "media_keep_muted".equals(type)) continue;
            if ("cabin_temperature".equals(type) && noCabin) continue;
            if ("cabin_fan".equals(type) && noCabin) continue;
            if ("climate_power".equals(type) && noCabin) continue;
            if ("window_position".equals(type) && noWindow) continue;
            if (type.startsWith("media_") && noMedia) continue;
            Map<String, Object> needed = TaskBinder.actionFor(goal);
            if (needed == null) continue;
            String needCap = String.valueOf(needed.get("capability_id"));
            boolean covered = draft.actions.stream()
                    .anyMatch(a -> aliasMatch(needCap, String.valueOf(a.get("capability_id"))));
            boolean assumedOk = draft.assumptions.stream()
                    .anyMatch(s -> s.contains(type) && (s.contains("already satisfied")
                            || s.contains("不产生写动作") || s.contains("skip")));
            boolean allDone = draft.actions.isEmpty() && draft.assumptions.stream()
                    .anyMatch(s -> s.contains("已满足") || s.contains("无需写动作"));
            if (!covered && !assumedOk && !allDone) {
                result.missingGoals.add(type + " → " + needCap);
            }
        }

        if (!result.violatedConstraints.isEmpty() || !result.riskyActions.isEmpty()) {
            result.decision = ReviewDecision.REJECT;
            result.suggestions.add("移除违规动作或收紧 allowed_capabilities 后重试");
            return result;
        }
        if (!result.missingGoals.isEmpty()) {
            result.decision = ReviewDecision.REVISE;
            result.suggestions.add("补齐遗漏目标对应的候选动作：" + String.join(", ", result.missingGoals));
            return result;
        }
        result.decision = ReviewDecision.PASS;
        return result;
    }

    /** Inject a deliberate omission for tests: drop first climate action. */
    public static PlanDraft omitClimateActions(PlanDraft draft) {
        PlanDraft copy = new PlanDraft();
        copy.runId = draft.runId;
        copy.goalVersion = draft.goalVersion;
        copy.modelId = draft.modelId;
        copy.revisionRound = draft.revisionRound;
        copy.assumptions = new ArrayList<>(draft.assumptions);
        copy.unresolved = new ArrayList<>(draft.unresolved);
        int i = 0;
        for (Map<String, Object> a : draft.actions) {
            if (String.valueOf(a.get("capability_id")).startsWith("climate.")) continue;
            copy.actions.add(a);
            copy.order.add(i++);
        }
        return copy;
    }

    private static boolean hasConstraint(List<Map<String, Object>> constraints, String type) {
        return constraints != null && constraints.stream().anyMatch(c -> type.equals(c.get("type")));
    }

    private static Map<String, Object> act(String capabilityId, Map<String, Object> params, String reason) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("decision", "ACT");
        m.put("capability_id", capabilityId);
        m.put("params", params);
        m.put("reason", reason);
        return m;
    }
}
