package com.deviceagent.capability;

import org.springframework.stereotype.Component;
import java.util.*;

/** The registered schema is shared by Tool Calling, Policy and the simulator. */
@Component
public class CapabilityRegistry {
    public static final String VERSION = "capabilities-v3";
    public static final List<String> WINDOWS = List.of("front_left", "front_right", "rear_left", "rear_right");
    public static final List<String> ROUTE_PREFERENCES = List.of(
            "fastest", "shortest", "avoid_highway", "avoid_congestion", "less_toll", "less_detour");

    private final Map<String, CapabilityDefinition> capabilities = new LinkedHashMap<>();

    public CapabilityRegistry() {
        add("device.get_state", "读取设备当前状态", false, "CABIN", Map.of());

        add("climate.set_power", "设置空调电源，不改变舱温", true, "CABIN", Map.of("value", bool()));
        add("climate.set_temperature", "设置整舱设定温度16至30℃，不代表当前舱温", true, "CABIN", Map.of("value", integer(16, 30)));
        add("climate.set_fan", "设置整舱风量1至3档", true, "CABIN", Map.of("value", integer(1, 3)));
        add("window.set_position", "车窗开度0关闭、100全开", true, "CABIN", Map.of(
                "window", Map.of("type", "string", "enum", List.of("front_left", "front_right", "rear_left", "rear_right", "all")),
                "position", integer(0, 100)));

        add("media.play", "播放占位媒体元数据，不输出真实音频", true, "MEDIA", Map.of("artist", str(80)));
        add("media.pause", "暂停媒体", true, "MEDIA", Map.of());
        add("media.set_volume", "媒体音量0至10，不改变导航音量或静音", true, "MEDIA", Map.of("value", integer(0, 10)));

        // 出行导航：可信执行（对齐场景化导航原则；search 失败不假成功）
        add("navigation.start", "发起导航开航：明确目的地直接开航；search 无候选则诚实失败", true, "NAVIGATION", Map.of("destination", str(120)));
        add("navigation.stop", "结束/退出当前导航", true, "NAVIGATION", Map.of());
        add("navigation.pause", "暂停当前导航指引", true, "NAVIGATION", Map.of());
        add("navigation.resume", "继续已暂停的导航", true, "NAVIGATION", Map.of());
        add("navigation.add_waypoint", "追加途经点；必须已有终点，不得把途经当新终点", true, "NAVIGATION", Map.of("name", str(120)));
        add("navigation.remove_waypoint", "删除指定途经点并重规划", true, "NAVIGATION", Map.of("name", str(120)));
        add("navigation.set_preference", "切换路线偏好", true, "NAVIGATION", Map.of(
                "value", Map.of("type", "string", "enum", ROUTE_PREFERENCES)));
        add("navigation.navigate_home", "导航到收藏的家；句中若含途经信号应由规划层先拆多点，禁止本能力抢跑", true, "NAVIGATION", Map.of());
        add("navigation.navigate_company", "导航到收藏的公司；句中若含途经信号应由规划层先拆多点，禁止本能力抢跑", true, "NAVIGATION", Map.of());
        add("navigation.set_home", "设置家地址收藏", true, "NAVIGATION", Map.of("place", str(120)));
        add("navigation.set_company", "设置公司地址收藏", true, "NAVIGATION", Map.of("place", str(120)));
        add("navigation.query_eta", "查询剩余时间/ETA；未在导航中须诚实说明", true, "NAVIGATION", Map.of());
        add("navigation.query_status", "查询当前导航状态与目的地", true, "NAVIGATION", Map.of());
        add("navigation.query_waypoints", "查询当前途经点列表", true, "NAVIGATION", Map.of());
        add("navigation.set_prompt_enabled", "设置导航提示开关，不代表用户听到了声音", true, "NAVIGATION", Map.of("value", bool()));
        add("navigation.set_volume", "设置导航独立音量0至10", true, "NAVIGATION", Map.of("value", integer(0, 10)));
        add("navigation.set_muted", "兼容诊断：设置导航静音", true, "NAVIGATION", Map.of("value", bool()));

        // 生活服务：仅接口 stub，会话/抢域逻辑见面试 QA；不实现真实点单业务
        add("life.search_shops", "生活服务：搜店（接口 stub）", true, "LIFE", Map.of("keyword", str(80)));
        add("life.enter_shop", "生活服务：进店（接口 stub）", true, "LIFE", Map.of("shop_name", str(80)));
        add("life.add_to_cart", "生活服务：加购（接口 stub）", true, "LIFE", Map.of("item", str(80)));
        add("life.go_to_checkout", "生活服务：去结算（接口 stub）", true, "LIFE", Map.of());
        add("life.close", "生活服务：关闭外卖会话（接口 stub）", true, "LIFE", Map.of());

        alias("cabin.set_temperature", "climate.set_temperature");
        alias("cabin.set_fan", "climate.set_fan");
        alias("device.read_state", "device.get_state");
        alias("navigation.set_route", "navigation.start");
        alias("navigation.exit", "navigation.stop");
        alias("navigation.nav_exit", "navigation.stop");
    }

    private static Map<String, Object> integer(int min, int max) {
        return Map.of("type", "integer", "minimum", min, "maximum", max);
    }

    private static Map<String, Object> bool() {
        return Map.of("type", "boolean");
    }

    private static Map<String, Object> str(int max) {
        return Map.of("type", "string", "minLength", 1, "maxLength", max);
    }

    private void add(String id, String desc, boolean write, String domain, Map<String, Object> props) {
        capabilities.put(id, new CapabilityDefinition(
                id, VERSION, desc, write, Set.of(domain),
                Map.of("type", "object", "properties", props, "required", new ArrayList<>(props.keySet()), "additionalProperties", false)));
    }

    private void alias(String alias, String id) {
        capabilities.put(alias, capabilities.get(id));
    }

    public Optional<CapabilityDefinition> get(String id) {
        return Optional.ofNullable(capabilities.get(id));
    }

    public Collection<CapabilityDefinition> all() {
        return new LinkedHashSet<>(capabilities.values());
    }

    public String canonical(String id) {
        return get(id).map(CapabilityDefinition::getId).orElse(id);
    }

    public List<Map<String, Object>> tools() {
        return all().stream()
                .map(c -> Map.<String, Object>of(
                        "type", "function",
                        "function", Map.of(
                                "name", wireName(c.getId()),
                                "description", c.getDescription(),
                                "parameters", c.getSchema())))
                .toList();
    }

    public static String wireName(String id) {
        return id.replace('.', '_');
    }

    public String fromWire(String name) {
        return all().stream().map(CapabilityDefinition::getId)
                .filter(id -> wireName(id).equals(name))
                .findFirst()
                .orElse(name);
    }

    @SuppressWarnings("unchecked")
    public ValidationResult validate(String id, Map<String, Object> params) {
        var d = capabilities.get(id);
        if (d == null) return ValidationResult.deny("UNKNOWN_CAPABILITY", "未注册能力: " + id);
        if (params == null) return ValidationResult.deny("SCHEMA", "参数必须是对象");
        Map<String, Object> props = (Map<String, Object>) d.getSchema().get("properties");
        if (!params.keySet().equals(props.keySet())) {
            return ValidationResult.deny("SCHEMA", "参数字段必须为 " + props.keySet());
        }
        for (var e : props.entrySet()) {
            Map<String, Object> s = (Map<String, Object>) e.getValue();
            Object v = params.get(e.getKey());
            String t = (String) s.get("type");
            boolean ok = switch (t) {
                case "integer" -> v instanceof Number n && Double.isFinite(n.doubleValue())
                        && n.doubleValue() == n.intValue()
                        && n.intValue() >= (int) s.get("minimum")
                        && n.intValue() <= (int) s.get("maximum");
                case "boolean" -> v instanceof Boolean;
                case "string" -> v instanceof String x && !x.isBlank()
                        && x.length() <= ((Number) s.getOrDefault("maxLength", 120)).intValue()
                        && (!s.containsKey("enum") || ((List<?>) s.get("enum")).contains(x));
                default -> false;
            };
            if (!ok) return ValidationResult.deny("SCHEMA", "非法参数: " + e.getKey() + "，不截断执行");
        }
        return ValidationResult.ok(d);
    }

    public record ValidationResult(boolean ok, String code, String message, CapabilityDefinition definition) {
        public static ValidationResult ok(CapabilityDefinition d) {
            return new ValidationResult(true, null, null, d);
        }

        public static ValidationResult deny(String c, String m) {
            return new ValidationResult(false, c, m, null);
        }
    }
}
