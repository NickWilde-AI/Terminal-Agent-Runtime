"""Built-in smart-terminal capability pack."""

from __future__ import annotations

from typing import Any

from terminal_agent.capability.domain_module import CapabilityRegistrar
from terminal_agent.capability.schemas import bool_schema, integer_schema, str_schema

WINDOWS = ["front_left", "front_right", "rear_left", "rear_right"]
ROUTE_PREFERENCES = [
    "fastest",
    "shortest",
    "avoid_highway",
    "avoid_congestion",
    "less_toll",
    "less_detour",
]


class TerminalDomainModule:
    def id(self) -> str:
        return "terminal"

    def register(self, r: CapabilityRegistrar) -> None:
        r.add("device.get_state", "读取设备当前状态", False, "CABIN", {})

        r.add("climate.set_power", "设置空调电源，不改变舱温", True, "CABIN", {"value": bool_schema()})
        r.add(
            "climate.set_temperature",
            "设置整舱设定温度16至30℃，不代表当前舱温",
            True,
            "CABIN",
            {"value": integer_schema(16, 30)},
        )
        r.add("climate.set_fan", "设置整舱风量1至3档", True, "CABIN", {"value": integer_schema(1, 3)})
        r.add(
            "window.set_position",
            "车窗开度0关闭、100全开",
            True,
            "CABIN",
            {
                "window": {
                    "type": "string",
                    "enum": ["front_left", "front_right", "rear_left", "rear_right", "all"],
                },
                "position": integer_schema(0, 100),
            },
        )

        r.add("media.play", "播放占位媒体元数据，不输出真实音频", True, "MEDIA", {"artist": str_schema(80)})
        r.add("media.pause", "暂停媒体", True, "MEDIA", {})
        r.add(
            "media.set_volume",
            "媒体音量0至10，不改变导航音量或静音",
            True,
            "MEDIA",
            {"value": integer_schema(0, 10)},
        )

        r.add(
            "navigation.start",
            "发起导航开航：明确目的地直接开航；search 无候选则诚实失败",
            True,
            "NAVIGATION",
            {"destination": str_schema(120)},
        )
        r.add("navigation.stop", "结束/退出当前导航", True, "NAVIGATION", {})
        r.add("navigation.pause", "暂停当前导航指引", True, "NAVIGATION", {})
        r.add("navigation.resume", "继续已暂停的导航", True, "NAVIGATION", {})
        r.add(
            "navigation.add_waypoint",
            "追加途经点；必须已有终点，不得把途经当新终点",
            True,
            "NAVIGATION",
            {"name": str_schema(120)},
        )
        r.add(
            "navigation.remove_waypoint",
            "删除指定途经点并重规划",
            True,
            "NAVIGATION",
            {"name": str_schema(120)},
        )
        r.add(
            "navigation.set_preference",
            "切换路线偏好",
            True,
            "NAVIGATION",
            {"value": {"type": "string", "enum": list(ROUTE_PREFERENCES)}},
        )
        r.add(
            "navigation.navigate_home",
            "导航到收藏的家；句中若含途经信号应由规划层先拆多点，禁止本能力抢跑",
            True,
            "NAVIGATION",
            {},
        )
        r.add(
            "navigation.navigate_company",
            "导航到收藏的公司；句中若含途经信号应由规划层先拆多点，禁止本能力抢跑",
            True,
            "NAVIGATION",
            {},
        )
        r.add("navigation.set_home", "设置家地址收藏", True, "NAVIGATION", {"place": str_schema(120)})
        r.add("navigation.set_company", "设置公司地址收藏", True, "NAVIGATION", {"place": str_schema(120)})
        r.add("navigation.query_eta", "查询剩余时间/ETA；未在导航中须诚实说明", False, "NAVIGATION", {})
        r.add("navigation.query_status", "查询当前导航状态与目的地", False, "NAVIGATION", {})
        r.add("navigation.query_waypoints", "查询当前途经点列表", False, "NAVIGATION", {})
        r.add(
            "navigation.set_prompt_enabled",
            "设置导航提示开关，不代表用户听到了声音",
            True,
            "NAVIGATION",
            {"value": bool_schema()},
        )
        r.add("navigation.set_volume", "设置导航独立音量0至10", True, "NAVIGATION", {"value": integer_schema(0, 10)})
        r.add("navigation.set_muted", "兼容诊断：设置导航静音", True, "NAVIGATION", {"value": bool_schema()})

        r.add("life.search_shops", "生活服务：搜店（接口 stub）", True, "LIFE", {"keyword": str_schema(80)})
        r.add("life.enter_shop", "生活服务：进店（接口 stub）", True, "LIFE", {"shop_name": str_schema(80)})
        r.add("life.add_to_cart", "生活服务：加购（接口 stub）", True, "LIFE", {"item": str_schema(80)})
        r.add("life.go_to_checkout", "生活服务：去结算（接口 stub）", True, "LIFE", {})
        r.add("life.close", "生活服务：关闭外卖会话（接口 stub）", True, "LIFE", {})

        r.alias("cabin.set_temperature", "climate.set_temperature")
        r.alias("cabin.set_fan", "climate.set_fan")
        r.alias("device.read_state", "device.get_state")
        r.alias("navigation.set_route", "navigation.start")
        r.alias("navigation.exit", "navigation.stop")
        r.alias("navigation.nav_exit", "navigation.stop")
