package com.deviceagent.harness;

import com.deviceagent.domain.StateSnapshot;
import com.deviceagent.model.CompiledTaskCandidate;
import com.deviceagent.model.ModelOutputNormalizer;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Deterministic NL → structured goals/constraints. Model candidates must cover every
 * detected user intent; missing coverage forces CLARIFY instead of false COMPLETED.
 */
public final class GoalCompiler {
    private static final Pattern TEMP = Pattern.compile("(?:空调|温度|设定).*?(\\d{1,2})\\s*度?");
    private static final Pattern TEMP_ALT = Pattern.compile("设为\\s*(\\d{1,2})");
    private static final Pattern FAN = Pattern.compile("风量.*?(\\d)");
    private static final Pattern MEDIA_ABS = Pattern.compile("媒体(?:音量)?.*?设为\\s*(\\d{1,2})");
    private static final Pattern WINDOW_POS = Pattern.compile(
            "(?:(左前|右前|左后|右后|前排左|前排右|后排左|后排右|全部|所有)?\\s*车窗|(?:打开|开)\\s*(左前|右前|左后|右后)?\\s*(?:车窗|窗)).*?(?:一半|(\\d{1,3})\\s*%?)?");
    private static final Pattern PLAY = Pattern.compile("播放\\s*([\\u4e00-\\u9fa5A-Za-z0-9·•\\- ]{1,40})");
    private static final Pattern NAV_TO = Pattern.compile("(?:导航(?:到|去)|去)\\s*([\\u4e00-\\u9fa5A-Za-z0-9]{2,40})");
    private static final Pattern WAYPOINT = Pattern.compile("(?:途经|顺便|顺路)(?:一个|家|去)?\\s*([\\u4e00-\\u9fa5A-Za-z0-9]{2,40})");
    private static final Pattern ADD_WAYPOINT = Pattern.compile("(?:加(?:个|一个)?途经点|途经点)\\s*([\\u4e00-\\u9fa5A-Za-z0-9]{2,40})");
    private static final Pattern REMOVE_WAYPOINT = Pattern.compile("(?:删除|去掉|取消)途经点\\s*([\\u4e00-\\u9fa5A-Za-z0-9]{2,40})");

    private GoalCompiler() {}

    public static CompiledTaskCandidate compile(
            String userText,
            StateSnapshot observation,
            List<Map<String, Object>> memoryHints
    ) {
        String text = userText == null ? "" : userText.trim();
        CompiledTaskCandidate c = new CompiledTaskCandidate();
        c.raw.put("compiler", "GoalCompiler");
        c.raw.put("input", text);
        c.raw.put("memory_hints", memoryHints == null ? List.of() : memoryHints);

        String focus = preferUserSupplement(text);
        Set<String> intents = detectIntents(text, focus);

        if (intents.isEmpty() && isChatOnly(text)) {
            c.routeHint = "CHAT";
            c.summary = chatReply(text);
            c.raw.put("agent_role", "MAIN");
            return c;
        }

        if ((text.contains("别改当前") || text.contains("不要改当前") || text.contains("但别改"))
                && !(focus.contains("允许") || focus.contains("保持不变") || focus.contains("改成"))) {
            c.routeHint = "CLARIFY";
            c.clarifyQuestion = "当前设定与目标冲突：要改成新温度，还是保持现状？请明确（例如：允许23 / 保持不变）";
            c.summary = "温度目标与保持现状冲突，需澄清";
            return c;
        }

        bindConstraints(text, c);

        // Explicit conflict: user asks to open window while also saying 不要开窗
        if (intents.contains("window") && hasNoWindow(text) && !focus.contains("允许开窗")) {
            c.routeHint = "REJECT";
            c.rejectReason = "约束禁止开窗";
            c.summary = "用户同时要求开窗与不要开窗，拒绝";
            return c;
        }

        Integer temp = extractTemp(focus);
        if (temp == null && focus.matches("\\d{1,2}")) temp = Integer.parseInt(focus);
        if (temp == null && focus.contains("允许")) {
            Matcher allow = Pattern.compile("允许\\s*(\\d{1,2})").matcher(focus);
            if (allow.find()) temp = Integer.parseInt(allow.group(1));
        }
        if (temp != null && (temp < 16 || temp > 30) && looksLikeSimpleSet(focus + text)) {
            c.routeHint = "CLARIFY";
            c.clarifyQuestion = "空调设定有效范围是 16—30℃，请给出有效温度（例如 24）";
            c.summary = "温度超范围，需澄清";
            return c;
        }

        boolean complex = isComplex(text) || intents.size() > 1
                || text.contains("休息") || text.contains("舒服")
                || (text.contains("导航") && (text.contains("没有声音") || text.contains("无声")))
                || intents.contains("nav_add_waypoint") && (intents.contains("nav_start") || intents.contains("nav_home") || intents.contains("nav_company"));

        if (!complex && intents.size() == 1) {
            if (intents.contains("temperature") && temp != null && looksLikeSimpleSet(focus + text)) {
                addGoal(c, "cabin_temperature", temp, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "climate.set_temperature", "params", Map.of("value", temp));
                c.summary = "明确设置空调温度为 " + temp + "℃";
                ensureCoverage(c, intents);
                return c;
            }
            Integer fan = firstNonNull(extractFan(focus), extractFan(text));
            if (intents.contains("fan") && fan != null) {
                int f = Math.max(1, Math.min(3, fan));
                addGoal(c, "cabin_fan", f, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "climate.set_fan", "params", Map.of("value", f));
                c.summary = "明确设置风量为 " + f;
                ensureCoverage(c, intents);
                return c;
            }
            Integer mediaAbs = firstNonNull(extractMediaAbs(focus), extractMediaAbs(text));
            if (intents.contains("media_volume") && mediaAbs != null) {
                addGoal(c, "media_volume", mediaAbs, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "media.set_volume", "params", Map.of("value", mediaAbs));
                c.summary = "明确设置媒体音量为 " + mediaAbs;
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("climate_power") && (text.contains("打开空调") || text.contains("开启空调"))) {
                addGoal(c, "climate_power", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "climate.set_power", "params", Map.of("value", true));
                c.summary = "打开空调电源";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("climate_power") && (text.contains("关闭空调") || text.contains("关掉空调"))) {
                addGoal(c, "climate_power", false, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "climate.set_power", "params", Map.of("value", false));
                c.summary = "关闭空调电源";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("window") && !hasNoWindow(text)) {
                WindowIntent w = extractWindow(text);
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "window_position");
                goal.put("window", w.window());
                goal.put("position", w.position());
                goal.put("source", "user");
                c.goals.add(goal);
                c.routeHint = "FAST";
                c.fastAction = Map.of(
                        "capability_id", "window.set_position",
                        "params", Map.of("window", w.window(), "position", w.position())
                );
                c.summary = "设置车窗 " + w.window() + " = " + w.position();
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("media_play")) {
                String artist = extractArtist(text);
                if (artist == null || artist.isBlank()) {
                    c.routeHint = "CLARIFY";
                    c.clarifyQuestion = "请说明要播放哪位艺人或哪首歌";
                    c.summary = "播放对象不明";
                    return c;
                }
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "media_play");
                goal.put("artist", artist);
                goal.put("source", "user");
                c.goals.add(goal);
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "media.play", "params", Map.of("artist", artist));
                c.summary = "播放 " + artist;
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("media_pause")) {
                addGoal(c, "media_pause", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "media.pause", "params", Map.of());
                c.summary = "暂停媒体";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_start")) {
                String dest = extractDestination(text);
                if (dest == null) {
                    c.routeHint = "CLARIFY";
                    c.clarifyQuestion = "请说明导航目的地";
                    c.summary = "目的地不明";
                    return c;
                }
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "nav_start");
                goal.put("destination", dest);
                goal.put("source", "user");
                c.goals.add(goal);
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.start", "params", Map.of("destination", dest));
                c.summary = "导航到 " + dest;
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_home")) {
                addGoal(c, "nav_home", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.navigate_home", "params", Map.of());
                c.summary = "导航回家";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_company")) {
                addGoal(c, "nav_company", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.navigate_company", "params", Map.of());
                c.summary = "导航去公司";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_stop")) {
                addGoal(c, "nav_stop", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.stop", "params", Map.of());
                c.summary = "停止导航";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_pause")) {
                addGoal(c, "nav_pause", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.pause", "params", Map.of());
                c.summary = "暂停导航";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_resume")) {
                addGoal(c, "nav_resume", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.resume", "params", Map.of());
                c.summary = "继续导航";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_query_eta")) {
                addGoal(c, "nav_query_eta", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.query_eta", "params", Map.of());
                c.summary = "查询 ETA";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_query_status")) {
                addGoal(c, "nav_query_status", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.query_status", "params", Map.of());
                c.summary = "查询导航状态";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_query_waypoints")) {
                addGoal(c, "nav_query_waypoints", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.query_waypoints", "params", Map.of());
                c.summary = "查询途经点";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_preference")) {
                String pref = extractPreference(text);
                if (pref == null) {
                    c.routeHint = "CLARIFY";
                    c.clarifyQuestion = "请说明路线偏好（最快/最短/不走高速/躲避拥堵）";
                    c.summary = "偏好不明";
                    return c;
                }
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "nav_preference");
                goal.put("value", pref);
                goal.put("source", "user");
                c.goals.add(goal);
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.set_preference", "params", Map.of("value", pref));
                c.summary = "切换路线偏好为 " + pref;
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_add_waypoint")) {
                String wp = extractWaypoint(text);
                Map<String, Object> state = observation == null ? Map.of() : observation.getState();
                boolean hasDest = Boolean.TRUE.equals(state.get("navigation_active")) && state.get("navigation_destination") != null;
                if (!hasDest) {
                    c.routeHint = "CLARIFY";
                    c.clarifyQuestion = "当前没有导航终点，请先说目的地，再加途经点";
                    c.summary = "无终点不可加途经";
                    return c;
                }
                if (wp == null) {
                    c.routeHint = "CLARIFY";
                    c.clarifyQuestion = "请说明要追加的途经点";
                    c.summary = "途经点不明";
                    return c;
                }
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "nav_add_waypoint");
                goal.put("name", wp);
                goal.put("source", "user");
                c.goals.add(goal);
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.add_waypoint", "params", Map.of("name", wp));
                c.summary = "追加途经点 " + wp;
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("nav_prompt") && (text.contains("开启导航播报") || text.contains("打开导航播报"))) {
                addGoal(c, "nav_prompt_enabled", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "navigation.set_prompt_enabled", "params", Map.of("value", true));
                c.summary = "开启导航播报";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("life_search_shops")) {
                String keyword = extractLifeKeyword(text);
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "life_search_shops");
                goal.put("keyword", keyword == null ? "美食" : keyword);
                goal.put("source", "user");
                c.goals.add(goal);
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "life.search_shops",
                        "params", Map.of("keyword", keyword == null ? "美食" : keyword));
                c.summary = "生活服务搜店：" + (keyword == null ? "美食" : keyword);
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("life_enter_shop")) {
                String shop = extractLifeShop(text);
                if (shop == null) {
                    c.routeHint = "CLARIFY";
                    c.clarifyQuestion = "请说明要进入哪家店";
                    c.summary = "进店对象不明";
                    return c;
                }
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "life_enter_shop");
                goal.put("shop_name", shop);
                goal.put("source", "user");
                c.goals.add(goal);
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "life.enter_shop", "params", Map.of("shop_name", shop));
                c.summary = "进入店铺 " + shop;
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("life_add_to_cart")) {
                String item = extractLifeItem(text);
                if (item == null) {
                    c.routeHint = "CLARIFY";
                    c.clarifyQuestion = "请说明要加购什么";
                    c.summary = "加购对象不明";
                    return c;
                }
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "life_add_to_cart");
                goal.put("item", item);
                goal.put("source", "user");
                c.goals.add(goal);
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "life.add_to_cart", "params", Map.of("item", item));
                c.summary = "加购 " + item;
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("life_go_to_checkout")) {
                addGoal(c, "life_go_to_checkout", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "life.go_to_checkout", "params", Map.of());
                c.summary = "去结算";
                ensureCoverage(c, intents);
                return c;
            }
            if (intents.contains("life_close")) {
                addGoal(c, "life_close", true, "user");
                c.routeHint = "FAST";
                c.fastAction = Map.of("capability_id", "life.close", "params", Map.of());
                c.summary = "关闭外卖会话";
                ensureCoverage(c, intents);
                return c;
            }
        }

        if (complex || intents.size() > 1 || text.contains("休息") || text.contains("舒服")
                || (text.contains("导航") && (text.contains("没有声音") || text.contains("无声")))) {
            c.routeHint = "MULTI_AGENT";
            bindComplex(text, observation, c, memoryHints, intents, temp);
            ensureCoverage(c, intents);
            if ("CLARIFY".equals(c.routeHint)) return c;
            c.summary = c.summary == null ? "复杂/多域任务，进入 MULTI_AGENT" : c.summary;
            c.raw.put("agent_role", "MAIN");
            ModelOutputNormalizer.normalize(c, text);
            return c;
        }

        if (text.contains("调低") && text.contains("声音") && !text.contains("媒体")) {
            c.routeHint = "CLARIFY";
            c.clarifyQuestion = "请确认要调低的是媒体音量还是导航音量？例如：媒体设为 4";
            c.summary = "作用对象不明";
            return c;
        }

        c.routeHint = "CLARIFY";
        c.clarifyQuestion = "请更明确地说明要设置的对象和数值";
        c.summary = "无法解析";
        return c;
    }

    private static void bindComplex(
            String text,
            StateSnapshot observation,
            CompiledTaskCandidate c,
            List<Map<String, Object>> memoryHints,
            Set<String> intents,
            Integer explicitTemp
    ) {
        Map<String, Object> state = observation == null ? Map.of() : observation.getState();
        boolean rest = text.contains("休息") || text.contains("舒服");
        boolean navSilent = text.contains("没有声音") || text.contains("无声");
        boolean noCabin = text.contains("不调空调") || text.contains("空调先不要");
        boolean keepNav = text.contains("保留导航") || text.contains("导航提示");

        Integer memTemp = memoryInt(memoryHints, "cabin_temperature");
        Integer memFan = memoryInt(memoryHints, "cabin_fan");

        if (intents.contains("climate_power") || text.contains("打开空调")) {
            if (!noCabin) addGoal(c, "climate_power", true, "user");
        }
        if (intents.contains("temperature") || (rest && !noCabin)) {
            if (!noCabin) {
                int temp = 23;
                String src = "demo-defaults-v1";
                if (explicitTemp != null) {
                    temp = explicitTemp;
                    src = "user";
                } else if (text.contains("24") && (text.contains("温度") || text.contains("明确"))) {
                    temp = 24;
                    src = "user";
                } else if (memTemp != null && memTemp >= 16 && memTemp <= 30) {
                    temp = memTemp;
                    src = "long_term_memory";
                }
                addGoal(c, "cabin_temperature", temp, src);
            }
        }
        if (intents.contains("fan") || (rest && !noCabin)) {
            if (!noCabin) {
                int fan = memFan != null && memFan >= 1 && memFan <= 3 ? memFan : 1;
                String fanSource = memFan != null ? "long_term_memory" : "demo-defaults-v1";
                addGoal(c, "cabin_fan", fan, fanSource);
            }
        }
        if (intents.contains("window") && !hasNoWindow(text)) {
            WindowIntent w = extractWindow(text);
            Map<String, Object> goal = new LinkedHashMap<>();
            goal.put("type", "window_position");
            goal.put("window", w.window());
            goal.put("position", w.position());
            goal.put("source", "user");
            c.goals.add(goal);
        }
        if (intents.contains("media_play")) {
            String artist = extractArtist(text);
            if (artist != null) {
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "media_play");
                goal.put("artist", artist);
                goal.put("source", "user");
                c.goals.add(goal);
            }
        }
        if (intents.contains("media_pause")) {
            addGoal(c, "media_pause", true, "user");
        }
        if (intents.contains("media_volume") || rest) {
            int mediaNow = ((Number) state.getOrDefault("media_volume", 8)).intValue();
            boolean muted = Boolean.TRUE.equals(state.get("media_muted"));
            if (!muted && (intents.contains("media_volume") || text.contains("媒体") || text.contains("声音调低"))) {
                Integer memMedia = memoryInt(memoryHints, "media_volume");
                int target = memMedia != null ? memMedia : Math.max(0, mediaNow - 2);
                String mediaSource = memMedia != null ? "long_term_memory" : "demo-defaults-v1";
                Map<String, Object> g = new LinkedHashMap<>();
                g.put("type", "media_volume");
                g.put("value", target);
                g.put("source", mediaSource);
                g.put("bound_from_observation", mediaNow);
                c.goals.add(g);
            } else if (muted && rest) {
                c.goals.add(Map.of("type", "media_keep_muted", "value", true, "source", "observation"));
            }
        }
        if (intents.contains("nav_start")) {
            String dest = extractDestination(text);
            if (dest != null) {
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "nav_start");
                goal.put("destination", dest);
                goal.put("source", "user");
                c.goals.add(goal);
            }
        }
        if (intents.contains("nav_home")) {
            addGoal(c, "nav_home", true, "user");
        }
        if (intents.contains("nav_company")) {
            addGoal(c, "nav_company", true, "user");
        }
        if (intents.contains("nav_add_waypoint")) {
            String wp = extractWaypoint(text);
            if (wp != null) {
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "nav_add_waypoint");
                goal.put("name", wp);
                goal.put("source", "user");
                c.goals.add(goal);
            }
        }
        if (intents.contains("nav_remove_waypoint")) {
            String wp = extractRemoveWaypoint(text);
            if (wp != null) {
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "nav_remove_waypoint");
                goal.put("name", wp);
                goal.put("source", "user");
                c.goals.add(goal);
            }
        }
        if (intents.contains("nav_preference")) {
            String pref = extractPreference(text);
            if (pref != null) {
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "nav_preference");
                goal.put("value", pref);
                goal.put("source", "user");
                c.goals.add(goal);
            }
        }
        if (intents.contains("nav_stop")) {
            addGoal(c, "nav_stop", true, "user");
        }
        if (intents.contains("nav_pause")) {
            addGoal(c, "nav_pause", true, "user");
        }
        if (intents.contains("nav_resume")) {
            addGoal(c, "nav_resume", true, "user");
        }
        if (intents.contains("nav_query_eta")) {
            addGoal(c, "nav_query_eta", true, "user");
        }
        if (intents.contains("nav_query_status")) {
            addGoal(c, "nav_query_status", true, "user");
        }
        if (intents.contains("nav_query_waypoints")) {
            addGoal(c, "nav_query_waypoints", true, "user");
        }
        if (intents.contains("life_search_shops")) {
            String keyword = extractLifeKeyword(text);
            Map<String, Object> goal = new LinkedHashMap<>();
            goal.put("type", "life_search_shops");
            goal.put("keyword", keyword == null ? "美食" : keyword);
            goal.put("source", "user");
            c.goals.add(goal);
        }
        if (intents.contains("life_enter_shop")) {
            String shop = extractLifeShop(text);
            if (shop != null) {
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "life_enter_shop");
                goal.put("shop_name", shop);
                goal.put("source", "user");
                c.goals.add(goal);
            }
        }
        if (intents.contains("life_add_to_cart")) {
            String item = extractLifeItem(text);
            if (item != null) {
                Map<String, Object> goal = new LinkedHashMap<>();
                goal.put("type", "life_add_to_cart");
                goal.put("item", item);
                goal.put("source", "user");
                c.goals.add(goal);
            }
        }
        if (intents.contains("life_go_to_checkout")) {
            addGoal(c, "life_go_to_checkout", true, "user");
        }
        if (intents.contains("life_close")) {
            addGoal(c, "life_close", true, "user");
        }
        if (keepNav) {
            c.criteria.add(criterion("nav_prompt_retained", Map.of(
                    "require_active", true,
                    "require_prompt_enabled", true,
                    "min_volume", state.getOrDefault("navigation_volume", 5)
            ), "user"));
        }
        if (navSilent) {
            if (Boolean.TRUE.equals(state.get("navigation_muted"))) {
                addGoal(c, "nav_muted", false, "user");
            }
            if (!Boolean.TRUE.equals(state.get("prompt_enabled"))) {
                addGoal(c, "nav_prompt_enabled", true, "user");
            }
            int navVol = ((Number) state.getOrDefault("navigation_volume", 0)).intValue();
            if (navVol == 0) {
                addGoal(c, "nav_volume", 3, "demo-defaults-v1");
            }
            c.criteria.add(criterion("nav_prompt_event_played", Map.of(), "user"));
        }
        if (intents.contains("nav_prompt") && !navSilent) {
            addGoal(c, "nav_prompt_enabled", true, "user");
        }
    }

    /** Fail closed: detected intents without matching goals → CLARIFY. */
    public static void ensureCoverage(CompiledTaskCandidate c, Set<String> intents) {
        if (c == null || intents == null || intents.isEmpty()) return;
        if ("REJECT".equals(c.routeHint) || "CLARIFY".equals(c.routeHint)) return;
        Set<String> covered = new LinkedHashSet<>();
        for (Map<String, Object> g : c.goals) {
            String type = String.valueOf(g.get("type"));
            switch (type) {
                case "climate_power" -> covered.add("climate_power");
                case "cabin_temperature" -> covered.add("temperature");
                case "cabin_fan" -> covered.add("fan");
                case "window_position" -> covered.add("window");
                case "media_play" -> covered.add("media_play");
                case "media_pause" -> covered.add("media_pause");
                case "media_volume", "media_keep_muted" -> covered.add("media_volume");
                case "nav_start" -> covered.add("nav_start");
                case "nav_stop" -> covered.add("nav_stop");
                case "nav_home" -> covered.add("nav_home");
                case "nav_company" -> covered.add("nav_company");
                case "nav_add_waypoint" -> covered.add("nav_add_waypoint");
                case "nav_remove_waypoint" -> covered.add("nav_remove_waypoint");
                case "nav_preference" -> covered.add("nav_preference");
                case "nav_pause" -> covered.add("nav_pause");
                case "nav_resume" -> covered.add("nav_resume");
                case "nav_query_eta" -> covered.add("nav_query_eta");
                case "nav_query_status" -> covered.add("nav_query_status");
                case "nav_query_waypoints" -> covered.add("nav_query_waypoints");
                case "nav_prompt_enabled" -> covered.add("nav_prompt");
                case "nav_volume", "nav_muted" -> covered.add("nav_diag");
                case "life_search_shops" -> covered.add("life_search_shops");
                case "life_enter_shop" -> covered.add("life_enter_shop");
                case "life_add_to_cart" -> covered.add("life_add_to_cart");
                case "life_go_to_checkout" -> covered.add("life_go_to_checkout");
                case "life_close" -> covered.add("life_close");
                default -> {}
            }
        }
        List<String> missing = new ArrayList<>();
        for (String intent : intents) {
            if ("nav_diag".equals(intent)) continue;
            if (!covered.contains(intent)) missing.add(intent);
        }
        if (!missing.isEmpty()) {
            c.routeHint = "CLARIFY";
            c.clarifyQuestion = "以下目标尚未绑定，请补充：" + String.join("、", missing);
            c.summary = "目标覆盖不完整: " + missing;
            c.raw.put("coverage_missing", missing);
        }
    }

    static boolean isChatOnly(String text) {
        if (text == null || text.isBlank()) return false;
        String t = text.trim();
        if (t.length() > 80) return false;
        if (t.contains("度") || t.contains("空调") || t.contains("风量") || t.contains("车窗")
                || t.contains("导航") || t.contains("媒体") || t.contains("音量") || t.contains("播放")
                || t.contains("设为") || t.contains("打开") || t.contains("关闭") || t.contains("调")
                || t.contains("途经") || t.contains("回家") || t.contains("公司") || t.contains("ETA")
                || t.contains("多久") || t.contains("外卖") || t.contains("点单")) {
            return false;
        }
        return t.matches(".*(你好|您好|在吗|谢谢|早上好|晚上好|哈哈|天气|心情|聊天).*")
                || t.equals("hi") || t.equalsIgnoreCase("hello") || t.length() <= 6;
    }

    static String chatReply(String text) {
        if (text != null && (text.contains("谢谢") || text.contains("感谢"))) {
            return "不客气。需要调空调、媒体或导航时直接说就行。";
        }
        if (text != null && (text.contains("天气") || text.contains("心情"))) {
            return "我可以帮你控制座舱设备；天气和闲聊我只能简单回应，有具体设置再说一声。";
        }
        return "你好，我是终端 Agent Runtime。可以说「把空调设为 23 度」或描述一个多约束座舱目标。";
    }

    public static Set<String> detectIntents(String text, String focus) {
        String t = (text == null ? "" : text) + " " + (focus == null ? "" : focus);
        Set<String> intents = new LinkedHashSet<>();
        if (t.contains("打开空调") || t.contains("开启空调") || t.contains("关闭空调") || t.contains("关掉空调")) {
            intents.add("climate_power");
        }
        if (extractTemp(t) != null || (t.contains("温度") && t.matches(".*\\d{1,2}.*"))
                || t.contains("设为") && (t.contains("度") || t.contains("空调"))) {
            intents.add("temperature");
        }
        if (t.contains("风量")) intents.add("fan");
        if (!hasNoWindow(t) && (t.contains("车窗") || t.contains("开窗") || t.contains("开一下窗"))) {
            intents.add("window");
        }
        if (t.contains("播放") && !t.contains("播报")) intents.add("media_play");
        if (t.contains("暂停") && (t.contains("媒体") || t.contains("音乐") || t.contains("播放"))) {
            intents.add("media_pause");
        }
        if (extractMediaAbs(t) != null || (t.contains("媒体") && (t.contains("音量") || t.contains("设为")))
                || (t.contains("声音调低") && t.contains("媒体"))) {
            intents.add("media_volume");
        }

        boolean multiPointSignal = t.contains("途经") || t.contains("顺路") || t.contains("顺便") || t.contains("加点");
        boolean goHome = t.contains("回家") || t.contains("导航回家") || t.matches(".*去家\\b.*");
        boolean goCompany = t.contains("去公司") || t.contains("导航去公司") || t.contains("导航到公司");

        // F-02：回家/公司 + 途经信号 → 交多点规划，禁止 favorite 抢跑成单一收藏开航
        if (goHome && multiPointSignal) {
            intents.add("nav_home");
            intents.add("nav_add_waypoint");
        } else if (goHome) {
            intents.add("nav_home");
        }
        if (goCompany && multiPointSignal) {
            intents.add("nav_company");
            intents.add("nav_add_waypoint");
        } else if (goCompany) {
            intents.add("nav_company");
        }

        if (!goHome && !goCompany
                && !t.contains("还有多久") && !t.contains("多久到") && !t.contains("预计到达")
                && !isLifeCheckoutPhrase(t)
                && (t.contains("导航到") || t.contains("导航去")
                || (extractDestination(t) != null && !isLifeOnlyPhrase(t))
                || (t.contains("导航") && t.contains("机场")))) {
            intents.add("nav_start");
        }
        if (multiPointSignal || ADD_WAYPOINT.matcher(t).find()) {
            intents.add("nav_add_waypoint");
        }
        if (REMOVE_WAYPOINT.matcher(t).find() || (t.contains("删除途经") || t.contains("去掉途经"))) {
            intents.add("nav_remove_waypoint");
        }
        if (t.contains("停止导航") || t.contains("结束导航") || t.contains("退出导航") || t.contains("取消导航")) {
            intents.add("nav_stop");
        }
        if (t.contains("暂停导航")) intents.add("nav_pause");
        if (t.contains("继续导航") || t.contains("恢复导航")) intents.add("nav_resume");
        if (t.contains("还有多久") || t.contains("多久到") || t.contains("ETA") || t.contains("eta") || t.contains("预计到达")) {
            intents.add("nav_query_eta");
        }
        if (t.contains("导航目的地") || t.contains("现在去哪里") || t.contains("当前目的地")) {
            intents.add("nav_query_status");
        }
        if (t.contains("途经点有哪些") || t.contains("有哪些途经")) {
            intents.add("nav_query_waypoints");
        }
        if (t.contains("不走高速") || t.contains("躲避拥堵") || t.contains("避开拥堵")
                || t.contains("最快路线") || t.contains("最短距离") || t.contains("少收费") || t.contains("少绕路")) {
            intents.add("nav_preference");
        }
        if (t.contains("开启导航播报") || t.contains("打开导航播报")) intents.add("nav_prompt");
        if (t.contains("没有声音") || t.contains("无声")) intents.add("nav_diag");

        // 生活服务：仅显式点单/外卖意图；「顺路咖啡」走导航途经，不进 life
        boolean explicitLife = t.contains("点外卖") || t.contains("外卖") || t.contains("美团") || t.contains("饿了么")
                || t.contains("搜店") || t.contains("点个外卖") || t.contains("叫外卖");
        boolean checkout = t.contains("去结算") || t.equals("结算") || t.contains("去结账") || t.contains("去买单");
        boolean closeLife = t.contains("关闭外卖") || t.contains("退出外卖") || t.contains("结束外卖") || t.contains("关掉外卖");
        if (explicitLife && !multiPointSignal) {
            intents.add("life_search_shops");
        }
        if (t.contains("进店") || t.contains("进入店铺")) {
            intents.add("life_enter_shop");
        }
        if (t.contains("加购") || (t.contains("加点") && explicitLife)) {
            intents.add("life_add_to_cart");
        }
        if (checkout) {
            intents.add("life_go_to_checkout");
        }
        if (closeLife) {
            intents.add("life_close");
        }
        return intents;
    }

    private static void bindConstraints(String text, CompiledTaskCandidate c) {
        if (hasNoWindow(text)) c.constraints.add(Map.of("type", "no_window", "source", "user"));
        if (text.contains("不要重启") || text.contains("不重启")) {
            c.constraints.add(Map.of("type", "no_reboot", "source", "user"));
        }
        if (text.contains("不调空调") || text.contains("空调先不要")) {
            c.constraints.add(Map.of("type", "no_cabin_write", "source", "user"));
        }
        if (text.contains("保留导航") || text.contains("导航提示")) {
            c.constraints.add(Map.of("type", "keep_navigation_prompt", "source", "user"));
        }
    }

    private static void addGoal(CompiledTaskCandidate c, String type, Object value, String source) {
        Map<String, Object> g = new LinkedHashMap<>();
        g.put("type", type);
        g.put("value", value);
        g.put("source", source);
        c.goals.add(g);
        String template = switch (type) {
            case "cabin_temperature" -> "cabin_temperature_eq";
            case "cabin_fan" -> "cabin_fan_eq";
            case "media_volume" -> "media_volume_eq";
            case "nav_prompt_enabled" -> "nav_prompt_enabled_eq";
            case "nav_muted" -> "nav_muted_eq";
            case "nav_volume" -> "nav_volume_eq";
            default -> null;
        };
        if (template != null) {
            c.criteria.add(criterion(template, Map.of("value", value), source));
        }
    }

    private static Map<String, Object> criterion(String templateId, Map<String, Object> params, String source) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("template_id", templateId);
        m.put("params", params);
        m.put("required", true);
        m.put("source", source);
        return m;
    }

    private record WindowIntent(String window, int position) {}

    private static WindowIntent extractWindow(String text) {
        String window = "all";
        if (text.contains("左前") || text.contains("前排左")) window = "front_left";
        else if (text.contains("右前") || text.contains("前排右")) window = "front_right";
        else if (text.contains("左后") || text.contains("后排左")) window = "rear_left";
        else if (text.contains("右后") || text.contains("后排右")) window = "rear_right";
        int position = 100;
        if (text.contains("一半") || text.contains("半开")) position = 50;
        Matcher m = Pattern.compile("(\\d{1,3})\\s*%").matcher(text);
        if (m.find()) position = Math.max(0, Math.min(100, Integer.parseInt(m.group(1))));
        Matcher m2 = WINDOW_POS.matcher(text);
        if (m2.find() && m2.group(3) != null) {
            position = Math.max(0, Math.min(100, Integer.parseInt(m2.group(3))));
        }
        return new WindowIntent(window, position);
    }

    private static String extractArtist(String text) {
        Matcher m = PLAY.matcher(text);
        if (!m.find()) return null;
        String raw = m.group(1).trim()
                .replaceAll("[，,。；;].*$", "")
                .replaceAll("(?:的歌|的音乐|音乐)$", "")
                .trim();
        return raw.isBlank() ? null : raw;
    }

    private static String extractDestination(String text) {
        if (text == null) return null;
        if (isLifeCheckoutPhrase(text) || isLifeOnlyPhrase(text)) return null;
        // strip waypoint clause before parsing destination
        String cleaned = text.replaceAll("(?:途经|顺便|顺路)(?:一个|家|去)?[\\u4e00-\\u9fa5A-Za-z0-9]{0,40}", " ");
        Matcher m = NAV_TO.matcher(cleaned);
        if (m.find()) {
            String dest = m.group(1).trim()
                    .replaceAll("[，,。；;].*$", "")
                    .replaceAll("(?:途经|顺便|顺路).*$", "")
                    .trim();
            if (dest.equals("家") || dest.equals("公司") || dest.isBlank()) return null;
            if (isBlockedNavDestination(dest)) return null;
            return dest;
        }
        if (cleaned.contains("虹桥机场")) return "虹桥机场";
        if (cleaned.contains("浦东机场")) return "浦东机场";
        if (cleaned.contains("东方明珠")) return "东方明珠";
        if (cleaned.contains("迪士尼")) return "迪士尼";
        if (cleaned.contains("固安")) return "固安";
        if (cleaned.contains("加油站")) return "加油站";
        if (cleaned.contains("星巴克")) return "星巴克";
        return null;
    }

    private static boolean isLifeCheckoutPhrase(String text) {
        if (text == null) return false;
        return text.contains("去结算") || text.contains("去结账") || text.contains("去买单")
                || text.trim().equals("结算") || text.trim().equals("结账");
    }

    /** 纯生活服务短句，禁止被「去X」误收成导航目的地。 */
    private static boolean isLifeOnlyPhrase(String text) {
        if (text == null) return false;
        String t = text.trim();
        return t.contains("点外卖") || t.contains("叫外卖") || t.contains("美团") || t.contains("饿了么")
                || t.contains("关闭外卖") || t.contains("退出外卖") || t.contains("搜店")
                || t.equals("结算") || t.equals("结账");
    }

    private static boolean isBlockedNavDestination(String dest) {
        if (dest == null) return true;
        return dest.equals("结算") || dest.equals("结账") || dest.equals("买单")
                || dest.equals("外卖") || dest.equals("美团") || dest.equals("饿了么");
    }

    private static String extractLifeKeyword(String text) {
        if (text == null) return null;
        if (text.contains("咖啡")) return "咖啡";
        if (text.contains("奶茶")) return "奶茶";
        if (text.contains("火锅")) return "火锅";
        if (text.contains("烧烤")) return "烧烤";
        Matcher m = Pattern.compile("(?:搜店|点外卖|叫外卖|找)\\s*([\\u4e00-\\u9fa5A-Za-z0-9]{1,20})").matcher(text);
        if (m.find()) {
            String k = m.group(1).trim();
            if (!k.equals("外卖") && !k.equals("美团")) return k;
        }
        return null;
    }

    private static String extractLifeShop(String text) {
        if (text == null) return null;
        Matcher m = Pattern.compile("(?:进店|进入)\\s*([\\u4e00-\\u9fa5A-Za-z0-9]{2,40})").matcher(text);
        if (m.find()) return m.group(1).trim();
        if (text.contains("星巴克")) return "星巴克";
        return null;
    }

    private static String extractLifeItem(String text) {
        if (text == null) return null;
        Matcher m = Pattern.compile("(?:加购|加点)\\s*([\\u4e00-\\u9fa5A-Za-z0-9]{1,40})").matcher(text);
        if (m.find()) return m.group(1).trim();
        return null;
    }

    private static String extractWaypoint(String text) {
        if (text == null) return null;
        Matcher add = ADD_WAYPOINT.matcher(text);
        if (add.find()) return add.group(1).trim();
        Matcher m = WAYPOINT.matcher(text);
        if (m.find()) return m.group(1).trim();
        if (text.contains("加油")) return "加油站";
        if (text.contains("咖啡") || text.contains("星巴克")) return "星巴克";
        return null;
    }

    private static String extractRemoveWaypoint(String text) {
        if (text == null) return null;
        Matcher m = REMOVE_WAYPOINT.matcher(text);
        return m.find() ? m.group(1).trim() : null;
    }

    private static String extractPreference(String text) {
        if (text == null) return null;
        if (text.contains("不走高速") || text.contains("避开高速")) return "avoid_highway";
        if (text.contains("躲避拥堵") || text.contains("避开拥堵")) return "avoid_congestion";
        if (text.contains("最短")) return "shortest";
        if (text.contains("少收费")) return "less_toll";
        if (text.contains("少绕路") || text.contains("防晕车")) return "less_detour";
        if (text.contains("最快") || text.contains("推荐路线")) return "fastest";
        return null;
    }

    private static Integer memoryInt(List<Map<String, Object>> hints, String key) {
        if (hints == null) return null;
        for (Map<String, Object> h : hints) {
            if (key.equals(String.valueOf(h.get("key")))) {
                try {
                    return Integer.parseInt(String.valueOf(h.get("value")));
                } catch (Exception ignored) {
                    return null;
                }
            }
        }
        return null;
    }

    private static String preferUserSupplement(String text) {
        if (text == null) return "";
        int i = text.lastIndexOf("用户补充：");
        if (i >= 0) return text.substring(i + "用户补充：".length()).trim();
        return text.trim();
    }

    private static boolean hasNoWindow(String text) {
        return text != null && (text.contains("不要开窗") || text.contains("不开窗") || text.contains("别开窗"));
    }

    private static boolean isComplex(String text) {
        if (text == null) return false;
        if (text.contains("用户补充：") || text.matches("媒体.*设为.*") || text.startsWith("允许")) {
            return text.contains("休息") || text.contains("舒服") || text.contains("检查");
        }
        return text.contains("休息") || text.contains("舒服") || text.contains("但是")
                || text.contains("保留") || text.contains("不要") || text.contains("检查")
                || text.contains("然后") || text.contains("并且") || text.contains("；")
                || ((text.contains("途经") || text.contains("顺路") || text.contains("顺便"))
                    && (text.contains("导航") || text.contains("回家") || text.contains("去公司") || text.contains("去")));
    }

    private static boolean looksLikeSimpleSet(String text) {
        if (text == null) return false;
        if (text.matches("\\d{1,2}") || text.matches("允许\\s*\\d{1,2}")) return true;
        return (text.contains("空调") || text.contains("温度") || text.contains("设为")) && !isComplex(text);
    }

    private static Integer extractTemp(String text) {
        if (text == null) return null;
        Matcher m = TEMP.matcher(text);
        if (m.find()) return Integer.parseInt(m.group(1));
        Matcher m2 = TEMP_ALT.matcher(text);
        if (m2.find() && (text.contains("空调") || text.contains("温度") || text.contains("度"))) {
            return Integer.parseInt(m2.group(1));
        }
        return null;
    }

    private static Integer extractFan(String text) {
        if (text == null) return null;
        Matcher m = FAN.matcher(text);
        return m.find() ? Integer.parseInt(m.group(1)) : null;
    }

    private static Integer extractMediaAbs(String text) {
        if (text == null) return null;
        Matcher m = MEDIA_ABS.matcher(text);
        return m.find() ? Integer.parseInt(m.group(1)) : null;
    }

    private static <T> T firstNonNull(T a, T b) {
        return a != null ? a : b;
    }
}
