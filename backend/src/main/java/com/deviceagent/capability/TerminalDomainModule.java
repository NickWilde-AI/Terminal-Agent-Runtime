package com.deviceagent.capability;

import java.util.List;
import java.util.Map;

/**
 * Built-in smart-terminal capability pack:
 * climate / window / media / navigation / life stubs.
 */
public final class TerminalDomainModule implements DomainModule {
    public static final List<String> WINDOWS = List.of("front_left", "front_right", "rear_left", "rear_right");
    public static final List<String> ROUTE_PREFERENCES = List.of(
            "fastest", "shortest", "avoid_highway", "avoid_congestion", "less_toll", "less_detour");

    @Override
    public String id() {
        return "terminal";
    }

    @Override
    public void register(CapabilityRegistrar r) {
        r.add("device.get_state", "读取设备当前状态", false, "CABIN", Map.of());

        r.add("climate.set_power", "设置空调电源，不改变舱温", true, "CABIN", Map.of("value", Schema.bool()));
        r.add("climate.set_temperature", "设置整舱设定温度16至30℃，不代表当前舱温", true, "CABIN",
                Map.of("value", Schema.integer(16, 30)));
        r.add("climate.set_fan", "设置整舱风量1至3档", true, "CABIN", Map.of("value", Schema.integer(1, 3)));
        r.add("window.set_position", "车窗开度0关闭、100全开", true, "CABIN", Map.of(
                "window", Map.of("type", "string", "enum", List.of(
                        "front_left", "front_right", "rear_left", "rear_right", "all")),
                "position", Schema.integer(0, 100)));

        r.add("media.play", "播放占位媒体元数据，不输出真实音频", true, "MEDIA", Map.of("artist", Schema.str(80)));
        r.add("media.pause", "暂停媒体", true, "MEDIA", Map.of());
        r.add("media.set_volume", "媒体音量0至10，不改变导航音量或静音", true, "MEDIA",
                Map.of("value", Schema.integer(0, 10)));

        r.add("navigation.start", "发起导航开航：明确目的地直接开航；search 无候选则诚实失败", true, "NAVIGATION",
                Map.of("destination", Schema.str(120)));
        r.add("navigation.stop", "结束/退出当前导航", true, "NAVIGATION", Map.of());
        r.add("navigation.pause", "暂停当前导航指引", true, "NAVIGATION", Map.of());
        r.add("navigation.resume", "继续已暂停的导航", true, "NAVIGATION", Map.of());
        r.add("navigation.add_waypoint", "追加途经点；必须已有终点，不得把途经当新终点", true, "NAVIGATION",
                Map.of("name", Schema.str(120)));
        r.add("navigation.remove_waypoint", "删除指定途经点并重规划", true, "NAVIGATION",
                Map.of("name", Schema.str(120)));
        r.add("navigation.set_preference", "切换路线偏好", true, "NAVIGATION", Map.of(
                "value", Map.of("type", "string", "enum", ROUTE_PREFERENCES)));
        r.add("navigation.navigate_home", "导航到收藏的家；句中若含途经信号应由规划层先拆多点，禁止本能力抢跑",
                true, "NAVIGATION", Map.of());
        r.add("navigation.navigate_company", "导航到收藏的公司；句中若含途经信号应由规划层先拆多点，禁止本能力抢跑",
                true, "NAVIGATION", Map.of());
        r.add("navigation.set_home", "设置家地址收藏", true, "NAVIGATION", Map.of("place", Schema.str(120)));
        r.add("navigation.set_company", "设置公司地址收藏", true, "NAVIGATION", Map.of("place", Schema.str(120)));
        r.add("navigation.query_eta", "查询剩余时间/ETA；未在导航中须诚实说明", true, "NAVIGATION", Map.of());
        r.add("navigation.query_status", "查询当前导航状态与目的地", true, "NAVIGATION", Map.of());
        r.add("navigation.query_waypoints", "查询当前途经点列表", true, "NAVIGATION", Map.of());
        r.add("navigation.set_prompt_enabled", "设置导航提示开关，不代表用户听到了声音", true, "NAVIGATION",
                Map.of("value", Schema.bool()));
        r.add("navigation.set_volume", "设置导航独立音量0至10", true, "NAVIGATION",
                Map.of("value", Schema.integer(0, 10)));
        r.add("navigation.set_muted", "兼容诊断：设置导航静音", true, "NAVIGATION", Map.of("value", Schema.bool()));

        r.add("life.search_shops", "生活服务：搜店（接口 stub）", true, "LIFE", Map.of("keyword", Schema.str(80)));
        r.add("life.enter_shop", "生活服务：进店（接口 stub）", true, "LIFE", Map.of("shop_name", Schema.str(80)));
        r.add("life.add_to_cart", "生活服务：加购（接口 stub）", true, "LIFE", Map.of("item", Schema.str(80)));
        r.add("life.go_to_checkout", "生活服务：去结算（接口 stub）", true, "LIFE", Map.of());
        r.add("life.close", "生活服务：关闭外卖会话（接口 stub）", true, "LIFE", Map.of());

        r.alias("cabin.set_temperature", "climate.set_temperature");
        r.alias("cabin.set_fan", "climate.set_fan");
        r.alias("device.read_state", "device.get_state");
        r.alias("navigation.set_route", "navigation.start");
        r.alias("navigation.exit", "navigation.stop");
        r.alias("navigation.nav_exit", "navigation.stop");
    }
}
