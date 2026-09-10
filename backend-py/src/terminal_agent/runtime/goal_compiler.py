"""Deterministic NL → structured goals/constraints.

Model candidates must cover every detected user intent; missing coverage forces
CLARIFY instead of a false COMPLETED.
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple

from terminal_agent.agent.contracts import CompiledTaskCandidate, StateSnapshot
from terminal_agent.model.normalizer import ModelOutputNormalizer

TEMP = re.compile(r"(?:空调|温度|设定).*?(\d{1,2})\s*度?")
TEMP_ALT = re.compile(r"设为\s*(\d{1,2})")
FAN = re.compile(r"风量.*?(\d)")
MEDIA_ABS = re.compile(r"媒体(?:音量)?.*?设为\s*(\d{1,2})")
WINDOW_POS = re.compile(
    r"(?:(左前|右前|左后|右后|前排左|前排右|后排左|后排右|全部|所有)?\s*车窗"
    r"|(?:打开|开)\s*(左前|右前|左后|右后)?\s*(?:车窗|窗)).*?(?:一半|(\d{1,3})\s*%?)?"
)
PLAY = re.compile(r"播放\s*([\u4e00-\u9fa5A-Za-z0-9·•\- ]{1,40})")
NAV_TO = re.compile(r"(?:导航(?:到|去)|去)\s*([\u4e00-\u9fa5A-Za-z0-9]{2,40})")
WAYPOINT = re.compile(r"(?:途经|顺便|顺路)(?:一个|家|去)?\s*([\u4e00-\u9fa5A-Za-z0-9]{2,40})")
ADD_WAYPOINT = re.compile(r"(?:加(?:个|一个)?途经点|途经点)\s*([\u4e00-\u9fa5A-Za-z0-9]{2,40})")
REMOVE_WAYPOINT = re.compile(r"(?:删除|去掉|取消)途经点\s*([\u4e00-\u9fa5A-Za-z0-9]{2,40})")

_ALLOW_TEMP = re.compile(r"允许\s*(\d{1,2})")
_PERCENT = re.compile(r"(\d{1,3})\s*%")
_LIFE_KEYWORD = re.compile(r"(?:搜店|点外卖|叫外卖|找)\s*([\u4e00-\u9fa5A-Za-z0-9]{1,20})")
_LIFE_SHOP = re.compile(r"(?:进店|进入)\s*([\u4e00-\u9fa5A-Za-z0-9]{2,40})")
_LIFE_ITEM = re.compile(r"(?:加购|加点)\s*([\u4e00-\u9fa5A-Za-z0-9]{1,40})")
_TWO_DIGITS = re.compile(r"\d{1,2}")
_ALLOW_TWO_DIGITS = re.compile(r"允许\s*\d{1,2}")
_ANY_TWO_DIGITS = re.compile(r".*\d{1,2}.*")
_CHAT_WORDS = re.compile(r".*(你好|您好|在吗|谢谢|早上好|晚上好|哈哈|天气|心情|聊天).*")
_MEDIA_SET = re.compile(r"媒体.*设为.*")
# Java's \b is ASCII-word based by default: "去家" only boundaries before an ASCII word char.
_GO_HOME_WORD = re.compile(r".*去家\b.*", re.ASCII)
_ARTIST_TAIL = re.compile(r"[，,。；;].*$")
_ARTIST_SUFFIX = re.compile(r"(?:的歌|的音乐|音乐)$")
_WAYPOINT_CLAUSE = re.compile(r"(?:途经|顺便|顺路)(?:一个|家|去)?[\u4e00-\u9fa5A-Za-z0-9]{0,40}")
_DEST_WAYPOINT_TAIL = re.compile(r"(?:途经|顺便|顺路).*$")

_USER_SUPPLEMENT = "用户补充："

_GOAL_CRITERION_TEMPLATES = {
    "cabin_temperature": "cabin_temperature_eq",
    "cabin_fan": "cabin_fan_eq",
    "media_volume": "media_volume_eq",
    "nav_prompt_enabled": "nav_prompt_enabled_eq",
    "nav_muted": "nav_muted_eq",
    "nav_volume": "nav_volume_eq",
    "light_power": "light_power_eq",
}

_COVERAGE_BY_GOAL_TYPE = {
    "climate_power": "climate_power",
    "cabin_temperature": "temperature",
    "cabin_fan": "fan",
    "window_position": "window",
    "media_play": "media_play",
    "media_pause": "media_pause",
    "media_volume": "media_volume",
    "media_keep_muted": "media_volume",
    "nav_start": "nav_start",
    "nav_stop": "nav_stop",
    "nav_home": "nav_home",
    "nav_company": "nav_company",
    "nav_add_waypoint": "nav_add_waypoint",
    "nav_remove_waypoint": "nav_remove_waypoint",
    "nav_preference": "nav_preference",
    "nav_pause": "nav_pause",
    "nav_resume": "nav_resume",
    "nav_query_eta": "nav_query_eta",
    "nav_query_status": "nav_query_status",
    "nav_query_waypoints": "nav_query_waypoints",
    "nav_prompt_enabled": "nav_prompt",
    "nav_volume": "nav_diag",
    "nav_muted": "nav_diag",
    "life_search_shops": "life_search_shops",
    "life_enter_shop": "life_enter_shop",
    "life_add_to_cart": "life_add_to_cart",
    "life_go_to_checkout": "life_go_to_checkout",
    "life_close": "life_close",
    "light_power": "light_power",
}


class WindowIntent(NamedTuple):
    window: str
    position: int


def compile(  # noqa: A001 - mirrors Java GoalCompiler.compile
    user_text: str | None,
    observation: StateSnapshot | None,
    memory_hints: list[dict[str, Any]] | None,
) -> CompiledTaskCandidate:
    text = "" if user_text is None else user_text.strip()
    c = CompiledTaskCandidate()
    c.raw["compiler"] = "GoalCompiler"
    c.raw["input"] = text
    c.raw["memory_hints"] = [] if memory_hints is None else memory_hints

    focus = prefer_user_supplement(text)
    intents = detect_intents(text, focus)

    if not intents and is_chat_only(text):
        c.route_hint = "CHAT"
        c.summary = chat_reply(text)
        c.raw["agent_role"] = "MAIN"
        return c

    if ("别改当前" in text or "不要改当前" in text or "但别改" in text) and not (
        "允许" in focus or "保持不变" in focus or "改成" in focus
    ):
        c.route_hint = "CLARIFY"
        c.clarify_question = "当前设定与目标冲突：要改成新温度，还是保持现状？请明确（例如：允许23 / 保持不变）"
        c.summary = "温度目标与保持现状冲突，需澄清"
        return c

    bind_constraints(text, c)

    # Explicit conflict: user asks to open window while also saying 不要开窗
    if "window" in intents and has_no_window(text) and "允许开窗" not in focus:
        c.route_hint = "REJECT"
        c.reject_reason = "约束禁止开窗"
        c.summary = "用户同时要求开窗与不要开窗，拒绝"
        return c

    temp = extract_temp(focus)
    if temp is None and _TWO_DIGITS.fullmatch(focus):
        temp = int(focus)
    if temp is None and "允许" in focus:
        allow = _ALLOW_TEMP.search(focus)
        if allow:
            temp = int(allow.group(1))
    if temp is not None and (temp < 16 or temp > 30) and looks_like_simple_set(focus + text):
        c.route_hint = "CLARIFY"
        c.clarify_question = "空调设定有效范围是 16—30℃，请给出有效温度（例如 24）"
        c.summary = "温度超范围，需澄清"
        return c

    complex_ = (
        is_complex(text)
        or len(intents) > 1
        or "休息" in text
        or "舒服" in text
        or ("导航" in text and ("没有声音" in text or "无声" in text))
        or (
            "nav_add_waypoint" in intents
            and ("nav_start" in intents or "nav_home" in intents or "nav_company" in intents)
        )
    )

    if not complex_ and len(intents) == 1:
        if "temperature" in intents and temp is not None and looks_like_simple_set(focus + text):
            add_goal(c, "cabin_temperature", temp, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "climate.set_temperature", "params": {"value": temp}}
            c.summary = f"明确设置空调温度为 {temp}℃"
            ensure_coverage(c, intents)
            return c
        fan = first_non_null(extract_fan(focus), extract_fan(text))
        if "fan" in intents and fan is not None:
            f = max(1, min(3, fan))
            add_goal(c, "cabin_fan", f, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "climate.set_fan", "params": {"value": f}}
            c.summary = f"明确设置风量为 {f}"
            ensure_coverage(c, intents)
            return c
        media_abs = first_non_null(extract_media_abs(focus), extract_media_abs(text))
        if "media_volume" in intents and media_abs is not None:
            add_goal(c, "media_volume", media_abs, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "media.set_volume", "params": {"value": media_abs}}
            c.summary = f"明确设置媒体音量为 {media_abs}"
            ensure_coverage(c, intents)
            return c
        if "climate_power" in intents and ("打开空调" in text or "开启空调" in text):
            add_goal(c, "climate_power", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "climate.set_power", "params": {"value": True}}
            c.summary = "打开空调电源"
            ensure_coverage(c, intents)
            return c
        if "climate_power" in intents and ("关闭空调" in text or "关掉空调" in text):
            add_goal(c, "climate_power", False, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "climate.set_power", "params": {"value": False}}
            c.summary = "关闭空调电源"
            ensure_coverage(c, intents)
            return c
        if "window" in intents and not has_no_window(text):
            w = extract_window(text)
            c.goals.append(
                {"type": "window_position", "window": w.window, "position": w.position, "source": "user"}
            )
            c.route_hint = "FAST"
            c.fast_action = {
                "capability_id": "window.set_position",
                "params": {"window": w.window, "position": w.position},
            }
            c.summary = f"设置车窗 {w.window} = {w.position}"
            ensure_coverage(c, intents)
            return c
        if "media_play" in intents:
            artist = extract_artist(text)
            if artist is None or not artist.strip():
                c.route_hint = "CLARIFY"
                c.clarify_question = "请说明要播放哪位艺人或哪首歌"
                c.summary = "播放对象不明"
                return c
            c.goals.append({"type": "media_play", "artist": artist, "source": "user"})
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "media.play", "params": {"artist": artist}}
            c.summary = f"播放 {artist}"
            ensure_coverage(c, intents)
            return c
        if "media_pause" in intents:
            add_goal(c, "media_pause", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "media.pause", "params": {}}
            c.summary = "暂停媒体"
            ensure_coverage(c, intents)
            return c
        if "nav_start" in intents:
            dest = extract_destination(text)
            if dest is None:
                c.route_hint = "CLARIFY"
                c.clarify_question = "请说明导航目的地"
                c.summary = "目的地不明"
                return c
            c.goals.append({"type": "nav_start", "destination": dest, "source": "user"})
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.start", "params": {"destination": dest}}
            c.summary = f"导航到 {dest}"
            ensure_coverage(c, intents)
            return c
        if "nav_home" in intents:
            add_goal(c, "nav_home", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.navigate_home", "params": {}}
            c.summary = "导航回家"
            ensure_coverage(c, intents)
            return c
        if "nav_company" in intents:
            add_goal(c, "nav_company", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.navigate_company", "params": {}}
            c.summary = "导航去公司"
            ensure_coverage(c, intents)
            return c
        if "nav_stop" in intents:
            add_goal(c, "nav_stop", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.stop", "params": {}}
            c.summary = "停止导航"
            ensure_coverage(c, intents)
            return c
        if "nav_pause" in intents:
            add_goal(c, "nav_pause", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.pause", "params": {}}
            c.summary = "暂停导航"
            ensure_coverage(c, intents)
            return c
        if "nav_resume" in intents:
            add_goal(c, "nav_resume", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.resume", "params": {}}
            c.summary = "继续导航"
            ensure_coverage(c, intents)
            return c
        if "nav_query_eta" in intents:
            add_goal(c, "nav_query_eta", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.query_eta", "params": {}}
            c.summary = "查询 ETA"
            ensure_coverage(c, intents)
            return c
        if "nav_query_status" in intents:
            add_goal(c, "nav_query_status", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.query_status", "params": {}}
            c.summary = "查询导航状态"
            ensure_coverage(c, intents)
            return c
        if "nav_query_waypoints" in intents:
            add_goal(c, "nav_query_waypoints", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.query_waypoints", "params": {}}
            c.summary = "查询途经点"
            ensure_coverage(c, intents)
            return c
        if "nav_preference" in intents:
            pref = extract_preference(text)
            if pref is None:
                c.route_hint = "CLARIFY"
                c.clarify_question = "请说明路线偏好（最快/最短/不走高速/躲避拥堵）"
                c.summary = "偏好不明"
                return c
            c.goals.append({"type": "nav_preference", "value": pref, "source": "user"})
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.set_preference", "params": {"value": pref}}
            c.summary = f"切换路线偏好为 {pref}"
            ensure_coverage(c, intents)
            return c
        if "nav_add_waypoint" in intents:
            wp = extract_waypoint(text)
            state: dict[str, Any] = {} if observation is None else observation.state
            has_dest = state.get("navigation_active") is True and state.get("navigation_destination") is not None
            if not has_dest:
                c.route_hint = "CLARIFY"
                c.clarify_question = "当前没有导航终点，请先说目的地，再加途经点"
                c.summary = "无终点不可加途经"
                return c
            if wp is None:
                c.route_hint = "CLARIFY"
                c.clarify_question = "请说明要追加的途经点"
                c.summary = "途经点不明"
                return c
            c.goals.append({"type": "nav_add_waypoint", "name": wp, "source": "user"})
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.add_waypoint", "params": {"name": wp}}
            c.summary = f"追加途经点 {wp}"
            ensure_coverage(c, intents)
            return c
        if "nav_prompt" in intents and ("开启导航播报" in text or "打开导航播报" in text):
            add_goal(c, "nav_prompt_enabled", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "navigation.set_prompt_enabled", "params": {"value": True}}
            c.summary = "开启导航播报"
            ensure_coverage(c, intents)
            return c
        if "life_search_shops" in intents:
            keyword = extract_life_keyword(text)
            resolved = "美食" if keyword is None else keyword
            c.goals.append({"type": "life_search_shops", "keyword": resolved, "source": "user"})
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "life.search_shops", "params": {"keyword": resolved}}
            c.summary = "生活服务搜店：" + resolved
            ensure_coverage(c, intents)
            return c
        if "life_enter_shop" in intents:
            shop = extract_life_shop(text)
            if shop is None:
                c.route_hint = "CLARIFY"
                c.clarify_question = "请说明要进入哪家店"
                c.summary = "进店对象不明"
                return c
            c.goals.append({"type": "life_enter_shop", "shop_name": shop, "source": "user"})
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "life.enter_shop", "params": {"shop_name": shop}}
            c.summary = f"进入店铺 {shop}"
            ensure_coverage(c, intents)
            return c
        if "life_add_to_cart" in intents:
            item = extract_life_item(text)
            if item is None:
                c.route_hint = "CLARIFY"
                c.clarify_question = "请说明要加购什么"
                c.summary = "加购对象不明"
                return c
            c.goals.append({"type": "life_add_to_cart", "item": item, "source": "user"})
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "life.add_to_cart", "params": {"item": item}}
            c.summary = f"加购 {item}"
            ensure_coverage(c, intents)
            return c
        if "life_go_to_checkout" in intents:
            add_goal(c, "life_go_to_checkout", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "life.go_to_checkout", "params": {}}
            c.summary = "去结算"
            ensure_coverage(c, intents)
            return c
        if "life_close" in intents:
            add_goal(c, "life_close", True, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "life.close", "params": {}}
            c.summary = "关闭外卖会话"
            ensure_coverage(c, intents)
            return c
        if "light_power" in intents:
            on = (
                "打开灯" in text
                or "开灯" in text
                or "把灯打开" in text
                or "开启灯光" in text
                or "开一下灯" in text
            )
            off = (
                "关闭灯" in text
                or "关灯" in text
                or "把灯关掉" in text
                or "关掉灯" in text
                or "关一下灯" in text
            )
            if on == off:
                c.route_hint = "CLARIFY"
                c.clarify_question = "请说明是开灯还是关灯"
                c.summary = "灯光目标不明"
                return c
            add_goal(c, "light_power", on, "user")
            c.route_hint = "FAST"
            c.fast_action = {"capability_id": "iot.light.set_power", "params": {"value": on}}
            c.summary = "打开智能灯" if on else "关闭智能灯"
            ensure_coverage(c, intents)
            return c

    if (
        complex_
        or len(intents) > 1
        or "休息" in text
        or "舒服" in text
        or ("导航" in text and ("没有声音" in text or "无声" in text))
    ):
        c.route_hint = "MULTI_AGENT"
        bind_complex(text, observation, c, memory_hints, intents, temp)
        ensure_coverage(c, intents)
        if c.route_hint == "CLARIFY":
            return c
        c.summary = "复杂/多域任务，进入 MULTI_AGENT" if c.summary is None else c.summary
        c.raw["agent_role"] = "MAIN"
        ModelOutputNormalizer.normalize(c, text)
        return c

    if "调低" in text and "声音" in text and "媒体" not in text:
        c.route_hint = "CLARIFY"
        c.clarify_question = "请确认要调低的是媒体音量还是导航音量？例如：媒体设为 4"
        c.summary = "作用对象不明"
        return c

    c.route_hint = "CLARIFY"
    c.clarify_question = "请更明确地说明要设置的对象和数值"
    c.summary = "无法解析"
    return c


def bind_complex(
    text: str,
    observation: StateSnapshot | None,
    c: CompiledTaskCandidate,
    memory_hints: list[dict[str, Any]] | None,
    intents: list[str],
    explicit_temp: int | None,
) -> None:
    state: dict[str, Any] = {} if observation is None else observation.state
    rest = "休息" in text or "舒服" in text
    nav_silent = "没有声音" in text or "无声" in text
    no_cabin = "不调空调" in text or "空调先不要" in text
    keep_nav = "保留导航" in text or "导航提示" in text

    mem_temp = memory_int(memory_hints, "cabin_temperature")
    mem_fan = memory_int(memory_hints, "cabin_fan")

    if "climate_power" in intents or "打开空调" in text:
        if not no_cabin:
            add_goal(c, "climate_power", True, "user")
    if "temperature" in intents or (rest and not no_cabin):
        if not no_cabin:
            temp = 23
            src = "demo-defaults-v1"
            if explicit_temp is not None:
                temp = explicit_temp
                src = "user"
            elif "24" in text and ("温度" in text or "明确" in text):
                temp = 24
                src = "user"
            elif mem_temp is not None and 16 <= mem_temp <= 30:
                temp = mem_temp
                src = "long_term_memory"
            add_goal(c, "cabin_temperature", temp, src)
    if "fan" in intents or (rest and not no_cabin):
        if not no_cabin:
            fan = mem_fan if mem_fan is not None and 1 <= mem_fan <= 3 else 1
            fan_source = "long_term_memory" if mem_fan is not None else "demo-defaults-v1"
            add_goal(c, "cabin_fan", fan, fan_source)
    if "window" in intents and not has_no_window(text):
        w = extract_window(text)
        c.goals.append({"type": "window_position", "window": w.window, "position": w.position, "source": "user"})
    if "media_play" in intents:
        artist = extract_artist(text)
        if artist is not None:
            c.goals.append({"type": "media_play", "artist": artist, "source": "user"})
    if "media_pause" in intents:
        add_goal(c, "media_pause", True, "user")
    if "media_volume" in intents or rest:
        media_now = int(state.get("media_volume", 8))
        muted = state.get("media_muted") is True
        if not muted and ("media_volume" in intents or "媒体" in text or "声音调低" in text):
            mem_media = memory_int(memory_hints, "media_volume")
            target = mem_media if mem_media is not None else max(0, media_now - 2)
            media_source = "long_term_memory" if mem_media is not None else "demo-defaults-v1"
            c.goals.append(
                {
                    "type": "media_volume",
                    "value": target,
                    "source": media_source,
                    "bound_from_observation": media_now,
                }
            )
        elif muted and rest:
            c.goals.append({"type": "media_keep_muted", "value": True, "source": "observation"})
    if "nav_start" in intents:
        dest = extract_destination(text)
        if dest is not None:
            c.goals.append({"type": "nav_start", "destination": dest, "source": "user"})
    if "nav_home" in intents:
        add_goal(c, "nav_home", True, "user")
    if "nav_company" in intents:
        add_goal(c, "nav_company", True, "user")
    if "nav_add_waypoint" in intents:
        wp = extract_waypoint(text)
        if wp is not None:
            c.goals.append({"type": "nav_add_waypoint", "name": wp, "source": "user"})
    if "nav_remove_waypoint" in intents:
        wp = extract_remove_waypoint(text)
        if wp is not None:
            c.goals.append({"type": "nav_remove_waypoint", "name": wp, "source": "user"})
    if "nav_preference" in intents:
        pref = extract_preference(text)
        if pref is not None:
            c.goals.append({"type": "nav_preference", "value": pref, "source": "user"})
    if "nav_stop" in intents:
        add_goal(c, "nav_stop", True, "user")
    if "nav_pause" in intents:
        add_goal(c, "nav_pause", True, "user")
    if "nav_resume" in intents:
        add_goal(c, "nav_resume", True, "user")
    if "nav_query_eta" in intents:
        add_goal(c, "nav_query_eta", True, "user")
    if "nav_query_status" in intents:
        add_goal(c, "nav_query_status", True, "user")
    if "nav_query_waypoints" in intents:
        add_goal(c, "nav_query_waypoints", True, "user")
    if "life_search_shops" in intents:
        keyword = extract_life_keyword(text)
        c.goals.append(
            {"type": "life_search_shops", "keyword": "美食" if keyword is None else keyword, "source": "user"}
        )
    if "life_enter_shop" in intents:
        shop = extract_life_shop(text)
        if shop is not None:
            c.goals.append({"type": "life_enter_shop", "shop_name": shop, "source": "user"})
    if "life_add_to_cart" in intents:
        item = extract_life_item(text)
        if item is not None:
            c.goals.append({"type": "life_add_to_cart", "item": item, "source": "user"})
    if "life_go_to_checkout" in intents:
        add_goal(c, "life_go_to_checkout", True, "user")
    if "life_close" in intents:
        add_goal(c, "life_close", True, "user")
    if "light_power" in intents:
        on = "打开灯" in text or "开灯" in text or "把灯打开" in text or "开启灯光" in text
        off = "关闭灯" in text or "关灯" in text or "把灯关掉" in text or "关掉灯" in text
        if on ^ off:
            add_goal(c, "light_power", on, "user")
    if keep_nav:
        c.criteria.append(
            criterion(
                "nav_prompt_retained",
                {
                    "require_active": True,
                    "require_prompt_enabled": True,
                    "min_volume": state.get("navigation_volume", 5),
                },
                "user",
            )
        )
    if nav_silent:
        if state.get("navigation_muted") is True:
            add_goal(c, "nav_muted", False, "user")
        if state.get("prompt_enabled") is not True:
            add_goal(c, "nav_prompt_enabled", True, "user")
        nav_vol = int(state.get("navigation_volume", 0))
        if nav_vol == 0:
            add_goal(c, "nav_volume", 3, "demo-defaults-v1")
        c.criteria.append(criterion("nav_prompt_event_played", {}, "user"))
    if "nav_prompt" in intents and not nav_silent:
        add_goal(c, "nav_prompt_enabled", True, "user")


def ensure_coverage(c: CompiledTaskCandidate | None, intents: list[str] | None) -> None:
    """Fail closed: detected intents without matching goals → CLARIFY."""
    if c is None or intents is None or not intents:
        return
    if c.route_hint == "REJECT" or c.route_hint == "CLARIFY":
        return
    covered: dict[str, None] = {}
    for g in c.goals:
        mapped = _COVERAGE_BY_GOAL_TYPE.get(str(g.get("type")))
        if mapped is not None:
            covered[mapped] = None
    missing: list[str] = []
    for intent in intents:
        if intent == "nav_diag":
            continue
        if intent not in covered:
            missing.append(intent)
    if missing:
        c.route_hint = "CLARIFY"
        c.clarify_question = "以下目标尚未绑定，请补充：" + "、".join(missing)
        c.summary = "目标覆盖不完整: [" + ", ".join(missing) + "]"
        c.raw["coverage_missing"] = missing


def is_chat_only(text: str | None) -> bool:
    if text is None or not text.strip():
        return False
    t = text.strip()
    if len(t) > 80:
        return False
    for token in (
        "度", "空调", "风量", "车窗",
        "导航", "媒体", "音量", "播放",
        "设为", "打开", "关闭", "调",
        "途经", "回家", "公司", "ETA",
        "多久", "外卖", "点单",
    ):
        if token in t:
            return False
    return bool(_CHAT_WORDS.fullmatch(t)) or t == "hi" or t.lower() == "hello" or len(t) <= 6


def chat_reply(text: str | None) -> str:
    if text is not None and ("谢谢" in text or "感谢" in text):
        return "不客气。需要调空调、媒体或导航时直接说就行。"
    if text is not None and ("天气" in text or "心情" in text):
        return "我可以帮你控制座舱设备；天气和闲聊我只能简单回应，有具体设置再说一声。"
    return "你好，我是终端 Agent Runtime。可以说「把空调设为 23 度」或描述一个多约束座舱目标。"


def detect_intents(text: str | None, focus: str | None) -> list[str]:
    """Ordered, unique intent list (mirrors Java LinkedHashSet)."""
    t = ("" if text is None else text) + " " + ("" if focus is None else focus)
    intents: dict[str, None] = {}

    def add(name: str) -> None:
        intents.setdefault(name, None)

    if "打开空调" in t or "开启空调" in t or "关闭空调" in t or "关掉空调" in t:
        add("climate_power")
    if (
        extract_temp(t) is not None
        or ("温度" in t and bool(_ANY_TWO_DIGITS.fullmatch(t)))
        or ("设为" in t and ("度" in t or "空调" in t))
    ):
        add("temperature")
    if "风量" in t:
        add("fan")
    if not has_no_window(t) and ("车窗" in t or "开窗" in t or "开一下窗" in t):
        add("window")
    if "播放" in t and "播报" not in t:
        add("media_play")
    if "暂停" in t and ("媒体" in t or "音乐" in t or "播放" in t):
        add("media_pause")
    if (
        extract_media_abs(t) is not None
        or ("媒体" in t and ("音量" in t or "设为" in t))
        or ("声音调低" in t and "媒体" in t)
    ):
        add("media_volume")

    multi_point_signal = "途经" in t or "顺路" in t or "顺便" in t or "加点" in t
    go_home = "回家" in t or "导航回家" in t or bool(_GO_HOME_WORD.fullmatch(t))
    go_company = "去公司" in t or "导航去公司" in t or "导航到公司" in t

    # F-02：回家/公司 + 途经信号 → 交多点规划，禁止 favorite 抢跑成单一收藏开航
    if go_home and multi_point_signal:
        add("nav_home")
        add("nav_add_waypoint")
    elif go_home:
        add("nav_home")
    if go_company and multi_point_signal:
        add("nav_company")
        add("nav_add_waypoint")
    elif go_company:
        add("nav_company")

    if (
        not go_home
        and not go_company
        and "还有多久" not in t
        and "多久到" not in t
        and "预计到达" not in t
        and not is_life_checkout_phrase(t)
        and (
            "导航到" in t
            or "导航去" in t
            or (extract_destination(t) is not None and not is_life_only_phrase(t))
            or ("导航" in t and "机场" in t)
        )
    ):
        add("nav_start")
    if multi_point_signal or ADD_WAYPOINT.search(t):
        add("nav_add_waypoint")
    if REMOVE_WAYPOINT.search(t) or ("删除途经" in t or "去掉途经" in t):
        add("nav_remove_waypoint")
    if "停止导航" in t or "结束导航" in t or "退出导航" in t or "取消导航" in t:
        add("nav_stop")
    if "暂停导航" in t:
        add("nav_pause")
    if "继续导航" in t or "恢复导航" in t:
        add("nav_resume")
    if "还有多久" in t or "多久到" in t or "ETA" in t or "eta" in t or "预计到达" in t:
        add("nav_query_eta")
    if "导航目的地" in t or "现在去哪里" in t or "当前目的地" in t:
        add("nav_query_status")
    if "途经点有哪些" in t or "有哪些途经" in t:
        add("nav_query_waypoints")
    if (
        "不走高速" in t
        or "躲避拥堵" in t
        or "避开拥堵" in t
        or "最快路线" in t
        or "最短距离" in t
        or "少收费" in t
        or "少绕路" in t
    ):
        add("nav_preference")
    if "开启导航播报" in t or "打开导航播报" in t:
        add("nav_prompt")
    if "没有声音" in t or "无声" in t:
        add("nav_diag")

    # 生活服务：仅显式点单/外卖意图；「顺路咖啡」走导航途经，不进 life
    explicit_life = (
        "点外卖" in t
        or "外卖" in t
        or "美团" in t
        or "饿了么" in t
        or "搜店" in t
        or "点个外卖" in t
        or "叫外卖" in t
    )
    checkout = "去结算" in t or t == "结算" or "去结账" in t or "去买单" in t
    close_life = "关闭外卖" in t or "退出外卖" in t or "结束外卖" in t or "关掉外卖" in t
    if explicit_life and not multi_point_signal:
        add("life_search_shops")
    if "进店" in t or "进入店铺" in t:
        add("life_enter_shop")
    if "加购" in t or ("加点" in t and explicit_life):
        add("life_add_to_cart")
    if checkout:
        add("life_go_to_checkout")
    if close_life:
        add("life_close")
    if (
        "开灯" in t
        or "打开灯" in t
        or "关灯" in t
        or "关闭灯" in t
        or "把灯打开" in t
        or "把灯关掉" in t
        or "开启灯光" in t
        or "关掉灯" in t
    ) and "车灯" not in t:
        add("light_power")
    return list(intents)


def bind_constraints(text: str, c: CompiledTaskCandidate) -> None:
    if has_no_window(text):
        c.constraints.append({"type": "no_window", "source": "user"})
    if "不要重启" in text or "不重启" in text:
        c.constraints.append({"type": "no_reboot", "source": "user"})
    if "不调空调" in text or "空调先不要" in text:
        c.constraints.append({"type": "no_cabin_write", "source": "user"})
    if "保留导航" in text or "导航提示" in text:
        c.constraints.append({"type": "keep_navigation_prompt", "source": "user"})


def add_goal(c: CompiledTaskCandidate, type_: str, value: Any, source: str) -> None:
    c.goals.append({"type": type_, "value": value, "source": source})
    template = _GOAL_CRITERION_TEMPLATES.get(type_)
    if template is not None:
        c.criteria.append(criterion(template, {"value": value}, source))


def criterion(template_id: str, params: dict[str, Any], source: str) -> dict[str, Any]:
    return {"template_id": template_id, "params": params, "required": True, "source": source}


def extract_window(text: str) -> WindowIntent:
    window = "all"
    if "左前" in text or "前排左" in text:
        window = "front_left"
    elif "右前" in text or "前排右" in text:
        window = "front_right"
    elif "左后" in text or "后排左" in text:
        window = "rear_left"
    elif "右后" in text or "后排右" in text:
        window = "rear_right"
    position = 100
    if "一半" in text or "半开" in text:
        position = 50
    m = _PERCENT.search(text)
    if m:
        position = max(0, min(100, int(m.group(1))))
    m2 = WINDOW_POS.search(text)
    if m2 and m2.group(3) is not None:
        position = max(0, min(100, int(m2.group(3))))
    return WindowIntent(window, position)


def extract_artist(text: str) -> str | None:
    m = PLAY.search(text)
    if not m:
        return None
    raw = m.group(1).strip()
    raw = _ARTIST_TAIL.sub("", raw)
    raw = _ARTIST_SUFFIX.sub("", raw)
    raw = raw.strip()
    return None if not raw.strip() else raw


def extract_destination(text: str | None) -> str | None:
    if text is None:
        return None
    if is_life_checkout_phrase(text) or is_life_only_phrase(text):
        return None
    # strip waypoint clause before parsing destination
    cleaned = _WAYPOINT_CLAUSE.sub(" ", text)
    m = NAV_TO.search(cleaned)
    if m:
        dest = m.group(1).strip()
        dest = _ARTIST_TAIL.sub("", dest)
        dest = _DEST_WAYPOINT_TAIL.sub("", dest)
        dest = dest.strip()
        if dest == "家" or dest == "公司" or not dest.strip():
            return None
        if is_blocked_nav_destination(dest):
            return None
        return dest
    if "虹桥机场" in cleaned:
        return "虹桥机场"
    if "浦东机场" in cleaned:
        return "浦东机场"
    if "东方明珠" in cleaned:
        return "东方明珠"
    if "迪士尼" in cleaned:
        return "迪士尼"
    if "固安" in cleaned:
        return "固安"
    if "加油站" in cleaned:
        return "加油站"
    if "星巴克" in cleaned:
        return "星巴克"
    return None


def is_life_checkout_phrase(text: str | None) -> bool:
    if text is None:
        return False
    return (
        "去结算" in text
        or "去结账" in text
        or "去买单" in text
        or text.strip() == "结算"
        or text.strip() == "结账"
    )


def is_life_only_phrase(text: str | None) -> bool:
    """纯生活服务短句，禁止被「去X」误收成导航目的地。"""
    if text is None:
        return False
    t = text.strip()
    return (
        "点外卖" in t
        or "叫外卖" in t
        or "美团" in t
        or "饿了么" in t
        or "关闭外卖" in t
        or "退出外卖" in t
        or "搜店" in t
        or t == "结算"
        or t == "结账"
    )


def is_blocked_nav_destination(dest: str | None) -> bool:
    if dest is None:
        return True
    return dest in ("结算", "结账", "买单", "外卖", "美团", "饿了么")


def extract_life_keyword(text: str | None) -> str | None:
    if text is None:
        return None
    if "咖啡" in text:
        return "咖啡"
    if "奶茶" in text:
        return "奶茶"
    if "火锅" in text:
        return "火锅"
    if "烧烤" in text:
        return "烧烤"
    m = _LIFE_KEYWORD.search(text)
    if m:
        k = m.group(1).strip()
        if k != "外卖" and k != "美团":
            return k
    return None


def extract_life_shop(text: str | None) -> str | None:
    if text is None:
        return None
    m = _LIFE_SHOP.search(text)
    if m:
        return m.group(1).strip()
    if "星巴克" in text:
        return "星巴克"
    return None


def extract_life_item(text: str | None) -> str | None:
    if text is None:
        return None
    m = _LIFE_ITEM.search(text)
    if m:
        return m.group(1).strip()
    return None


def extract_waypoint(text: str | None) -> str | None:
    if text is None:
        return None
    add = ADD_WAYPOINT.search(text)
    if add:
        return add.group(1).strip()
    m = WAYPOINT.search(text)
    if m:
        return m.group(1).strip()
    if "加油" in text:
        return "加油站"
    if "咖啡" in text or "星巴克" in text:
        return "星巴克"
    return None


def extract_remove_waypoint(text: str | None) -> str | None:
    if text is None:
        return None
    m = REMOVE_WAYPOINT.search(text)
    return m.group(1).strip() if m else None


def extract_preference(text: str | None) -> str | None:
    if text is None:
        return None
    if "不走高速" in text or "避开高速" in text:
        return "avoid_highway"
    if "躲避拥堵" in text or "避开拥堵" in text:
        return "avoid_congestion"
    if "最短" in text:
        return "shortest"
    if "少收费" in text:
        return "less_toll"
    if "少绕路" in text or "防晕车" in text:
        return "less_detour"
    if "最快" in text or "推荐路线" in text:
        return "fastest"
    return None


def memory_int(hints: list[dict[str, Any]] | None, key: str) -> int | None:
    if hints is None:
        return None
    for h in hints:
        if key == str(h.get("key")):
            try:
                return int(str(h.get("value")))
            except Exception:
                return None
    return None


def prefer_user_supplement(text: str | None) -> str:
    if text is None:
        return ""
    i = text.rfind(_USER_SUPPLEMENT)
    if i >= 0:
        return text[i + len(_USER_SUPPLEMENT) :].strip()
    return text.strip()


def has_no_window(text: str | None) -> bool:
    return text is not None and ("不要开窗" in text or "不开窗" in text or "别开窗" in text)


def is_complex(text: str | None) -> bool:
    if text is None:
        return False
    if _USER_SUPPLEMENT in text or _MEDIA_SET.fullmatch(text) or text.startswith("允许"):
        return "休息" in text or "舒服" in text or "检查" in text
    return (
        "休息" in text
        or "舒服" in text
        or "但是" in text
        or "保留" in text
        or "不要" in text
        or "检查" in text
        or "然后" in text
        or "并且" in text
        or "；" in text
        or (
            ("途经" in text or "顺路" in text or "顺便" in text)
            and ("导航" in text or "回家" in text or "去公司" in text or "去" in text)
        )
    )


def looks_like_simple_set(text: str | None) -> bool:
    if text is None:
        return False
    if _TWO_DIGITS.fullmatch(text) or _ALLOW_TWO_DIGITS.fullmatch(text):
        return True
    return ("空调" in text or "温度" in text or "设为" in text) and not is_complex(text)


def extract_temp(text: str | None) -> int | None:
    if text is None:
        return None
    m = TEMP.search(text)
    if m:
        return int(m.group(1))
    m2 = TEMP_ALT.search(text)
    if m2 and ("空调" in text or "温度" in text or "度" in text):
        return int(m2.group(1))
    return None


def extract_fan(text: str | None) -> int | None:
    if text is None:
        return None
    m = FAN.search(text)
    return int(m.group(1)) if m else None


def extract_media_abs(text: str | None) -> int | None:
    if text is None:
        return None
    m = MEDIA_ABS.search(text)
    return int(m.group(1)) if m else None


def first_non_null(a: Any, b: Any) -> Any:
    return a if a is not None else b


# Pythonic function API plus a Java-shaped compatibility facade for callers
# ported incrementally from the original runtime.
compile_goal = compile


class GoalCompiler:
    compile = staticmethod(compile)
    detect_intents = staticmethod(detect_intents)
    ensure_coverage = staticmethod(ensure_coverage)
    is_chat_only = staticmethod(is_chat_only)
    chat_reply = staticmethod(chat_reply)
