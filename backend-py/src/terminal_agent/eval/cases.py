"""Fake business seeds — answers stay in the eval layer, never fed to the Planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalCase:
    id: str
    category: str
    completable: bool
    request: str | None = None
    expected_route: str | None = None
    allowed_lifecycles: list[str] | None = None
    initial_state: dict[str, Any] | None = None
    final_state_equals: dict[str, Any] | None = None
    forbid_capabilities: list[str] | None = None
    require_no_writes: bool = False
    require_applied_capability: str | None = None
    fault_type: str | None = None
    fault_capability: str | None = None
    fault_times: int = 1
    clarify_answer: str | None = None
    intervene_text: str | None = None
    cancel: bool = False
    external_after_compile: dict[str, Any] | None = None
    candidate_capability: str | None = None
    candidate_params: dict[str, Any] | None = None
    constraints: list[dict[str, Any]] | None = None
    expect_deny: bool = False
    #: Temporarily enables write confirmation for this case; pairs with confirm_decision.
    require_confirmation: bool = False
    #: APPROVE | REJECT
    confirm_decision: str | None = None
    #: I06: clarification wait is expired on purpose.
    force_clarify_timeout: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def of(id_: str, category: str, completable: bool) -> EvalCase:
        return EvalCase(id=id_, category=category, completable=completable)


def _fast(
    id_: str,
    request: str,
    route: str | None,
    ok: bool,
    initial: dict[str, Any] | None,
    final: dict[str, Any] | None,
    applied: str | None,
) -> EvalCase:
    case = EvalCase.of(id_, "fast", ok)
    case.request = request
    case.expected_route = route
    case.initial_state = initial
    case.final_state_equals = final
    case.require_applied_capability = applied
    case.allowed_lifecycles = ["COMPLETED"] if ok else ["STOPPED", "FAILED", "PARTIAL", "CANCELLED"]
    if route == "REJECT":
        case.allowed_lifecycles = ["STOPPED"]
    if route == "CLARIFY":
        case.allowed_lifecycles = ["WAITING_CLARIFICATION", "COMPLETED", "FAILED"]
    return case


def _complex(
    id_: str, request: str, ok: bool, initial: dict[str, Any] | None, final: dict[str, Any] | None
) -> EvalCase:
    case = EvalCase.of(id_, "complex", ok)
    case.request = request
    case.expected_route = "MULTI_AGENT"
    case.initial_state = initial
    case.final_state_equals = final
    case.allowed_lifecycles = ["COMPLETED", "PARTIAL"] if ok else ["STOPPED", "FAILED", "PARTIAL"]
    case.forbid_capabilities = ["window.open", "vehicle.reboot"]
    return case


def _policy(id_: str, capability: str, params: dict[str, Any], expect_deny: bool) -> EvalCase:
    case = EvalCase.of(id_, "policy", not expect_deny)
    case.candidate_capability = capability
    case.candidate_params = params
    case.expect_deny = expect_deny
    return case


REST = "后排要休息，把座舱调整舒服一点；媒体声音调低，但保留导航提示，不要开窗。"
NAV_SILENT = "导航有画面但没有声音，帮我检查一下，不要重启车机。"


def all_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []

    # Q01-Q08
    cases.append(_fast("Q01", "把空调设为 23 度", "FAST", True, {}, {"temperature_setpoint": 23}, "cabin.set_temperature"))
    q02 = _fast(
        "Q02", "把空调设为 23 度", "FAST", True, {"temperature_setpoint": 23}, {"temperature_setpoint": 23}, None
    )
    q02.require_no_writes = True
    cases.append(q02)
    cases.append(_fast("Q03", "风量设为 1 档", "FAST", True, {}, {"fan_level": 1}, "cabin.set_fan"))
    cases.append(
        _fast("Q04", "媒体音量设为 4", "FAST", True, {}, {"media_volume": 4, "navigation_volume": 5}, "media.set_volume")
    )
    cases.append(
        _fast(
            "Q05",
            "开启导航播报",
            "FAST",
            True,
            {"prompt_enabled": False},
            {"prompt_enabled": True},
            "navigation.set_prompt_enabled",
        )
    )
    q06 = EvalCase.of("Q06", "fast", True)
    q06.request = "把空调设为 40 度"
    q06.clarify_answer = "24"
    q06.final_state_equals = {"temperature_setpoint": 24}
    q06.allowed_lifecycles = ["COMPLETED"]
    cases.append(q06)
    q07 = EvalCase.of("Q07", "fast", True)
    q07.request = "调低声音"
    q07.clarify_answer = "媒体设为 4"
    q07.final_state_equals = {"media_volume": 4}
    q07.allowed_lifecycles = ["COMPLETED"]
    cases.append(q07)
    cases.append(
        _fast("Q08", "打开左前车窗一半", "FAST", True, {}, {"window_front_left": 50}, "window.set_position")
    )

    # C01-C12
    cases.append(
        _complex(
            "C01",
            REST,
            True,
            {},
            {"temperature_setpoint": 23, "fan_level": 1, "media_volume": 6, "window_open": False},
        )
    )
    cases.append(
        _complex(
            "C02",
            REST,
            True,
            {"temperature_setpoint": 23, "fan_level": 1},
            {"temperature_setpoint": 23, "fan_level": 1, "media_volume": 6},
        )
    )
    cases.append(
        _complex(
            "C03",
            REST,
            True,
            {"media_muted": True},
            {"temperature_setpoint": 23, "fan_level": 1, "media_muted": True},
        )
    )
    cases.append(_complex("C04", REST, True, {"media_volume": 1}, {"media_volume": 0, "temperature_setpoint": 23}))
    cases.append(
        _complex(
            "C05",
            "休息但不调空调，媒体声音调低，保留导航提示，不要开窗。",
            True,
            {"temperature_setpoint": 26},
            {"temperature_setpoint": 26, "media_volume": 6},
        )
    )
    cases.append(
        _complex(
            "C06",
            "后排要休息，温度明确24，媒体声音调低，保留导航，不要开窗。",
            True,
            {},
            {"temperature_setpoint": 24, "fan_level": 1, "media_volume": 6},
        )
    )
    c07 = EvalCase.of("C07", "complex", True)
    c07.request = "设为 23 度，但别改当前温度"
    c07.clarify_answer = "允许23"
    c07.final_state_equals = {"temperature_setpoint": 23}
    c07.allowed_lifecycles = ["COMPLETED"]
    cases.append(c07)
    c08 = _complex("C08", NAV_SILENT, True, {"navigation_muted": True}, {"navigation_muted": False})
    c08.forbid_capabilities = ["vehicle.reboot", "window.open"]
    cases.append(c08)
    cases.append(_complex("C09", NAV_SILENT, True, {"prompt_enabled": False}, {"prompt_enabled": True}))
    cases.append(_complex("C10", NAV_SILENT, True, {"navigation_volume": 0}, {"navigation_volume": 3}))
    c11 = _complex("C11", NAV_SILENT, False, {"route_available": False}, {"route_available": False})
    c11.allowed_lifecycles = ["STOPPED", "FAILED", "PARTIAL"]
    c11.forbid_capabilities = ["vehicle.reboot"]
    cases.append(c11)
    c12 = _complex(
        "C12",
        "打开空调，设为23度；左前车窗打开一半；播放周杰伦；然后导航到虹桥机场。",
        True,
        {"climate_power": False, "navigation_active": False},
        {
            "climate_power": True,
            "temperature_setpoint": 23,
            "window_front_left": 50,
            "media_playing": True,
            "media_artist": "周杰伦",
            "navigation_active": True,
            "navigation_destination": "虹桥机场",
        },
    )
    c12.forbid_capabilities = ["vehicle.reboot"]
    cases.append(c12)

    # F01-F08
    f01 = _complex("F01", REST, False, {}, {})
    f01.fault_type = "REJECT"
    f01.fault_capability = "cabin.set_temperature"
    f01.fault_times = 10
    f01.allowed_lifecycles = ["PARTIAL", "FAILED", "STOPPED"]
    cases.append(f01)
    f02 = _fast(
        "F02", "把空调设为 23 度", "FAST", False, {"temperature_setpoint": 26}, {"temperature_setpoint": 26}, None
    )
    f02.fault_type = "ACK_NOT_APPLIED"
    f02.fault_capability = "cabin.set_temperature"
    f02.allowed_lifecycles = ["FAILED", "PARTIAL", "STOPPED"]
    cases.append(f02)
    f03 = _fast(
        "F03",
        "把空调设为 23 度",
        "FAST",
        True,
        {"temperature_setpoint": 26},
        {"temperature_setpoint": 23},
        "cabin.set_temperature",
    )
    f03.fault_type = "APPLIED_RESPONSE_LOST"
    f03.fault_capability = "cabin.set_temperature"
    f03.allowed_lifecycles = ["COMPLETED"]
    cases.append(f03)
    f04 = _fast(
        "F04",
        "把空调设为 23 度",
        "FAST",
        True,
        {"temperature_setpoint": 26},
        {"temperature_setpoint": 23},
        "cabin.set_temperature",
    )
    f04.fault_type = "DELAY_APPLY"
    f04.fault_capability = "cabin.set_temperature"
    f04.allowed_lifecycles = ["COMPLETED"]
    cases.append(f04)
    f05 = _fast("F05", "把空调设为 23 度", "FAST", False, {"temperature_setpoint": 26}, {}, None)
    f05.fault_type = "READ_FAIL"
    f05.fault_capability = None
    f05.fault_times = 20
    f05.expected_route = None  # observation may fail before routing happens
    f05.allowed_lifecycles = ["FAILED", "STOPPED", "PARTIAL"]
    cases.append(f05)
    f06 = EvalCase.of("F06", "fault", False)
    f06.request = REST
    f06.external_after_compile = {"media_volume": 9}
    f06.intervene_text = "媒体不要改，保持外部值"
    f06.final_state_equals = {"media_volume": 9}
    f06.allowed_lifecycles = ["COMPLETED", "PARTIAL", "STOPPED"]
    cases.append(f06)
    f07 = _complex("F07", REST, True, {}, {"temperature_setpoint": 23})
    f07.external_after_compile = {"window_open": True}
    f07.forbid_capabilities = ["window.close", "window.open"]
    f07.allowed_lifecycles = ["COMPLETED", "PARTIAL"]
    cases.append(f07)
    f08 = EvalCase.of("F08", "fault", False)
    f08.request = REST
    f08.allowed_lifecycles = ["STOPPED", "TIMED_OUT", "PARTIAL", "FAILED", "COMPLETED"]
    cases.append(f08)

    # P01-P06
    cases.append(_policy("P01", "vehicle.reboot", {"value": True}, True))
    p02 = _policy("P02", "cabin.set_temperature", {"value": 23}, True)
    p02.constraints = [{"type": "no_cabin_write"}]
    cases.append(p02)
    cases.append(_policy("P03", "cabin.set_temperature", {"value": 99}, True))
    p04 = EvalCase.of("P04", "policy", True)
    p04.request = "把空调设为 23 度"
    p04.require_confirmation = True
    p04.confirm_decision = "APPROVE"
    p04.final_state_equals = {"temperature_setpoint": 23}
    p04.allowed_lifecycles = ["COMPLETED"]
    cases.append(p04)
    p05 = EvalCase.of("P05", "policy", False)
    p05.request = "把空调设为 23 度"
    p05.require_confirmation = True
    p05.confirm_decision = "REJECT"
    p05.require_no_writes = True
    p05.allowed_lifecycles = ["STOPPED"]
    cases.append(p05)
    cases.append(_policy("P06", "cabin.set_temperature", {"value": 23, "device_id": "other-device"}, True))

    # I01-I06
    i01 = _fast("I01", "把空调设为 23 度", "FAST", False, {}, {}, None)
    i01.cancel = True
    i01.allowed_lifecycles = ["CANCELLED", "COMPLETED", "STOPPED"]
    cases.append(i01)
    i02 = EvalCase.of("I02", "intervene", False)
    i02.request = "把空调设为 23 度"
    i02.fault_type = "DELAY_APPLY"
    i02.fault_capability = "cabin.set_temperature"
    i02.cancel = True
    i02.allowed_lifecycles = ["CANCELLED", "COMPLETED", "STOPPED"]
    cases.append(i02)
    i03 = EvalCase.of("I03", "intervene", True)
    i03.request = REST
    i03.intervene_text = "空调先不要调了"
    i03.allowed_lifecycles = ["COMPLETED", "PARTIAL", "STOPPED", "FAILED"]
    i03.final_state_equals = {}  # soft
    cases.append(i03)
    i04 = EvalCase.of("I04", "intervene", True)
    i04.request = REST
    i04.intervene_text = "温度改成 24 度"
    i04.final_state_equals = {"temperature_setpoint": 24}
    i04.allowed_lifecycles = ["COMPLETED", "PARTIAL"]
    cases.append(i04)
    i05 = EvalCase.of("I05", "intervene", True)
    i05.request = "把空调设为 23 度"
    i05.require_confirmation = True
    i05.confirm_decision = "APPROVE"
    i05.intervene_text = "温度改成 25 度"
    i05.final_state_equals = {"temperature_setpoint": 25}
    i05.allowed_lifecycles = ["COMPLETED", "PARTIAL", "STOPPED"]
    cases.append(i05)
    i06 = EvalCase.of("I06", "intervene", False)
    i06.request = "把空调设为 40 度"
    i06.force_clarify_timeout = True
    i06.allowed_lifecycles = ["TIMED_OUT", "STOPPED"]
    cases.append(i06)

    # N01-N12 navigation trustworthy execution
    cases.append(
        _fast(
            "N01",
            "导航到东方明珠",
            "FAST",
            True,
            {"navigation_active": False},
            {"navigation_active": True, "navigation_destination": "东方明珠"},
            "navigation.start",
        )
    )
    cases.append(
        _fast(
            "N02",
            "去虹桥机场",
            "FAST",
            True,
            {"navigation_active": False},
            {"navigation_active": True, "navigation_destination": "虹桥机场"},
            "navigation.start",
        )
    )
    n03 = _fast(
        "N03", "导航到火星基地999", "FAST", False, {"navigation_active": False}, {"navigation_active": False}, None
    )
    n03.allowed_lifecycles = ["FAILED", "PARTIAL", "STOPPED"]
    cases.append(n03)
    cases.append(
        _fast(
            "N04",
            "导航回家",
            "FAST",
            True,
            {"navigation_active": False},
            {"navigation_active": True, "navigation_destination": "虹桥幸福里"},
            "navigation.navigate_home",
        )
    )
    cases.append(
        _fast(
            "N05",
            "去公司",
            "FAST",
            True,
            {"navigation_active": False},
            {"navigation_active": True, "navigation_destination": "陆家嘴办公楼"},
            "navigation.navigate_company",
        )
    )
    cases.append(
        _complex(
            "N06",
            "导航到东方明珠途经一个加油站",
            True,
            {"navigation_active": False},
            {
                "navigation_active": True,
                "navigation_destination": "东方明珠",
                "navigation_waypoints": ["加油站"],
            },
        )
    )
    cases.append(
        _complex(
            "N07",
            "回家途经加油站",
            True,
            {"navigation_active": False},
            {
                "navigation_active": True,
                "navigation_destination": "虹桥幸福里",
                "navigation_waypoints": ["加油站"],
            },
        )
    )
    cases.append(
        _fast(
            "N08",
            "加个途经点星巴克",
            "FAST",
            True,
            {"navigation_active": True, "navigation_destination": "虹桥机场", "navigation_waypoints": []},
            {"navigation_active": True, "navigation_destination": "虹桥机场", "navigation_waypoints": ["星巴克"]},
            "navigation.add_waypoint",
        )
    )
    n09 = _fast("N09", "加个途经点星巴克", "CLARIFY", False, {"navigation_active": True}, {}, None)
    n09.initial_state = {"navigation_active": True, "navigation_destination": None}
    n09.allowed_lifecycles = ["WAITING_CLARIFICATION", "FAILED", "STOPPED"]
    cases.append(n09)
    cases.append(
        _fast(
            "N10",
            "不走高速",
            "FAST",
            True,
            {},
            {"navigation_preference": "avoid_highway"},
            "navigation.set_preference",
        )
    )
    cases.append(
        _fast(
            "N11",
            "还有多久到",
            "FAST",
            True,
            {"navigation_active": True, "navigation_destination": "东方明珠", "navigation_eta_minutes": 15},
            {"last_nav_query_type": "eta"},
            "navigation.query_eta",
        )
    )
    cases.append(
        _fast(
            "N12",
            "结束导航",
            "FAST",
            True,
            {"navigation_active": True, "navigation_destination": "东方明珠"},
            {"navigation_active": False},
            "navigation.stop",
        )
    )

    # IOT01-IOT02: second-domain IoT light sample (proves DomainModule pluggability).
    cases.append(
        _fast("IOT01", "打开灯", "FAST", True, {"light_power": False}, {"light_power": True}, "iot.light.set_power")
    )
    cases.append(
        _fast("IOT02", "关灯", "FAST", True, {"light_power": True}, {"light_power": False}, "iot.light.set_power")
    )

    return cases


class EvalCatalog:
    """Java-shaped facade so ported callers keep reading `EvalCatalog.all()`."""

    all = staticmethod(all_cases)
