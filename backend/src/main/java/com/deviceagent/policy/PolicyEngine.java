package com.deviceagent.policy;

import com.deviceagent.capability.CapabilityRegistry;
import com.deviceagent.config.DeviceAgentProperties;
import com.deviceagent.domain.PolicyDecision;
import com.deviceagent.domain.RunRecord;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.Objects;

@Component
public class PolicyEngine {
    private final CapabilityRegistry registry;
    private final DeviceAgentProperties properties;

    public PolicyEngine(CapabilityRegistry registry, DeviceAgentProperties properties) {
        this.registry = registry;
        this.properties = properties;
    }

    public Result decide(RunRecord run, String capabilityId, Map<String, Object> params) {
        var validation = registry.validate(capabilityId, params);
        if (!validation.ok()) {
            return Result.deny(validation.code(), validation.message());
        }

        List<Map<String, Object>> constraints = run.getTask().getConstraints();
        for (Map<String, Object> c : constraints) {
            String type = String.valueOf(c.getOrDefault("type", ""));
            if ("forbid_action".equals(type)) {
                Object forbidden = c.get("capability_id");
                if (capabilityId.equals(String.valueOf(forbidden))) {
                    return Result.deny("FORBIDDEN", "约束禁止分发: " + capabilityId);
                }
            }
            if ("no_cabin_write".equals(type) && (capabilityId.startsWith("cabin.") || capabilityId.startsWith("climate."))) {
                return Result.deny("FORBIDDEN", "约束：不调空调");
            }
            if ("no_media_write".equals(type) && capabilityId.startsWith("media.")) {
                return Result.deny("FORBIDDEN", "约束：不改媒体");
            }
            if ("no_window".equals(type) && capabilityId.contains("window")) {
                return Result.deny("FORBIDDEN", "约束：不要开窗");
            }
            if ("no_reboot".equals(type) && capabilityId.contains("reboot")) {
                return Result.deny("FORBIDDEN", "约束：不要重启");
            }
        }

        if (!registry.get(capabilityId).isPresent()) {
            return Result.deny("UNKNOWN_CAPABILITY", "未注册能力");
        }

        // P06：会话设备绑定 — 候选指定其他 device_id 时拒绝
        Object candidateDevice = params == null ? null : params.get("device_id");
        if (candidateDevice != null && run.getDeviceId() != null
                && !run.getDeviceId().equals(String.valueOf(candidateDevice))) {
            return Result.deny("DEVICE_MISMATCH", "候选设备不属于当前会话授权设备");
        }
        Object authorized = run.getTask().getBindingContext().get("authorized_device_id");
        if (authorized != null && run.getDeviceId() != null
                && !run.getDeviceId().equals(String.valueOf(authorized))) {
            return Result.deny("DEVICE_MISMATCH", "会话未授权该设备");
        }

        if (properties.isRequireConfirmation()
                && registry.get(capabilityId).map(c -> c.isWrite()).orElse(false)
                && !Boolean.TRUE.equals(run.getTask().getBindingContext().get("force_allow_write"))) {
            Object approved = run.getTask().getBindingContext().get("approved_action");
            if (approved instanceof Map<?, ?> m
                    && capabilityId.equals(String.valueOf(m.get("capability_id")))
                    && Objects.equals(m.get("params"), params)
                    && Objects.equals(m.get("goal_version"), run.getTask().getGoalVersion())) {
                // Single-shot approval bound to capability+params+version
                run.getTask().getBindingContext().remove("approved_action");
                return Result.allow();
            }
            return Result.confirm("演示策略：写操作需确认");
        }
        return Result.allow();
    }

    public record Result(PolicyDecision decision, String code, String message) {
        public static Result allow() { return new Result(PolicyDecision.ALLOW, null, null); }
        public static Result deny(String code, String message) { return new Result(PolicyDecision.DENY, code, message); }
        public static Result confirm(String message) { return new Result(PolicyDecision.REQUIRE_CONFIRMATION, "REQUIRE_CONFIRMATION", message); }
    }
}
