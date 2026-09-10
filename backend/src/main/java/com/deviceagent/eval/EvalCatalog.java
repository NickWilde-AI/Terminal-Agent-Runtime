package com.deviceagent.eval;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** 40 seed cases — answers stay in eval layer, never fed to Planner. */
public final class EvalCatalog {
    private EvalCatalog() {}

    public static List<EvalCase> all() {
        List<EvalCase> list = new ArrayList<>();
        // Q01-Q08
        list.add(q("Q01", "把空调设为 23 度", "FAST", true, Map.of(), Map.of("temperature_setpoint", 23), "cabin.set_temperature"));
        list.add(q("Q02", "把空调设为 23 度", "FAST", true, Map.of("temperature_setpoint", 23), Map.of("temperature_setpoint", 23), null));
        list.get(1).requireNoWrites = true;
        list.add(q("Q03", "风量设为 1 档", "FAST", true, Map.of(), Map.of("fan_level", 1), "cabin.set_fan"));
        list.add(q("Q04", "媒体音量设为 4", "FAST", true, Map.of(), Map.of("media_volume", 4, "navigation_volume", 5), "media.set_volume"));
        EvalCase q05 = q("Q05", "开启导航播报", "FAST", true, Map.of("prompt_enabled", false), Map.of("prompt_enabled", true), "navigation.set_prompt_enabled");
        list.add(q05);
        EvalCase q06 = EvalCase.of("Q06", "fast", true);
        q06.request = "把空调设为 40 度";
        q06.clarifyAnswer = "24";
        q06.finalStateEquals = Map.of("temperature_setpoint", 24);
        q06.allowedLifecycles = List.of("COMPLETED");
        list.add(q06);
        EvalCase q07 = EvalCase.of("Q07", "fast", true);
        q07.request = "调低声音";
        q07.clarifyAnswer = "媒体设为 4";
        q07.finalStateEquals = Map.of("media_volume", 4);
        q07.allowedLifecycles = List.of("COMPLETED");
        list.add(q07);
        EvalCase q08 = q("Q08", "打开左前车窗一半", "FAST", true,
                Map.of(), Map.of("window_front_left", 50), "window.set_position");
        list.add(q08);

        // C01-C12
        String rest = "后排要休息，把座舱调整舒服一点；媒体声音调低，但保留导航提示，不要开窗。";
        list.add(c("C01", rest, true, Map.of(), Map.of("temperature_setpoint", 23, "fan_level", 1, "media_volume", 6, "window_open", false)));
        list.add(c("C02", rest, true, Map.of("temperature_setpoint", 23, "fan_level", 1), Map.of("temperature_setpoint", 23, "fan_level", 1, "media_volume", 6)));
        list.add(c("C03", rest, true, Map.of("media_muted", true), Map.of("temperature_setpoint", 23, "fan_level", 1, "media_muted", true)));
        list.add(c("C04", rest, true, Map.of("media_volume", 1), Map.of("media_volume", 0, "temperature_setpoint", 23)));
        list.add(c("C05", "休息但不调空调，媒体声音调低，保留导航提示，不要开窗。", true,
                Map.of("temperature_setpoint", 26), Map.of("temperature_setpoint", 26, "media_volume", 6)));
        list.add(c("C06", "后排要休息，温度明确24，媒体声音调低，保留导航，不要开窗。", true,
                Map.of(), Map.of("temperature_setpoint", 24, "fan_level", 1, "media_volume", 6)));
        EvalCase c07 = EvalCase.of("C07", "complex", true);
        c07.request = "设为 23 度，但别改当前温度";
        c07.clarifyAnswer = "允许23";
        c07.finalStateEquals = Map.of("temperature_setpoint", 23);
        c07.allowedLifecycles = List.of("COMPLETED");
        list.add(c07);
        String navSilent = "导航有画面但没有声音，帮我检查一下，不要重启车机。";
        list.add(c("C08", navSilent, true, Map.of("navigation_muted", true), Map.of("navigation_muted", false)));
        list.get(list.size() - 1).forbidCapabilities = List.of("vehicle.reboot", "window.open");
        list.add(c("C09", navSilent, true, Map.of("prompt_enabled", false), Map.of("prompt_enabled", true)));
        list.add(c("C10", navSilent, true, Map.of("navigation_volume", 0), Map.of("navigation_volume", 3)));
        EvalCase c11 = c("C11", navSilent, false, Map.of("route_available", false), Map.of("route_available", false));
        c11.allowedLifecycles = List.of("STOPPED", "FAILED", "PARTIAL");
        c11.forbidCapabilities = List.of("vehicle.reboot");
        list.add(c11);
        list.add(c("C12", "打开空调，设为23度；左前车窗打开一半；播放周杰伦；然后导航到虹桥机场。", true,
                Map.of("climate_power", false, "navigation_active", false),
                Map.of("climate_power", true, "temperature_setpoint", 23, "window_front_left", 50,
                        "media_playing", true, "media_artist", "周杰伦", "navigation_active", true,
                        "navigation_destination", "虹桥机场")));
        list.get(list.size() - 1).forbidCapabilities = List.of("vehicle.reboot");

        // F01-F08
        EvalCase f01 = c("F01", rest, false, Map.of(), Map.of());
        f01.faultType = "REJECT";
        f01.faultCapability = "cabin.set_temperature";
        f01.faultTimes = 10;
        f01.allowedLifecycles = List.of("PARTIAL", "FAILED", "STOPPED");
        list.add(f01);
        EvalCase f02 = q("F02", "把空调设为 23 度", "FAST", false, Map.of("temperature_setpoint", 26), Map.of("temperature_setpoint", 26), null);
        f02.faultType = "ACK_NOT_APPLIED";
        f02.faultCapability = "cabin.set_temperature";
        f02.allowedLifecycles = List.of("FAILED", "PARTIAL", "STOPPED");
        list.add(f02);
        EvalCase f03 = q("F03", "把空调设为 23 度", "FAST", true, Map.of("temperature_setpoint", 26), Map.of("temperature_setpoint", 23), "cabin.set_temperature");
        f03.faultType = "APPLIED_RESPONSE_LOST";
        f03.faultCapability = "cabin.set_temperature";
        f03.allowedLifecycles = List.of("COMPLETED");
        list.add(f03);
        EvalCase f04 = q("F04", "把空调设为 23 度", "FAST", true, Map.of("temperature_setpoint", 26), Map.of("temperature_setpoint", 23), "cabin.set_temperature");
        f04.faultType = "DELAY_APPLY";
        f04.faultCapability = "cabin.set_temperature";
        f04.allowedLifecycles = List.of("COMPLETED");
        list.add(f04);
        EvalCase f05 = q("F05", "把空调设为 23 度", "FAST", false, Map.of("temperature_setpoint", 26), Map.of(), null);
        f05.faultType = "READ_FAIL";
        f05.faultCapability = null;
        f05.faultTimes = 20;
        f05.expectedRoute = null; // 观察失败时可能尚未路由
        f05.allowedLifecycles = List.of("FAILED", "STOPPED", "PARTIAL");
        list.add(f05);
        EvalCase f06 = EvalCase.of("F06", "fault", false);
        f06.request = rest;
        f06.externalAfterCompile = Map.of("media_volume", 9);
        f06.interveneText = "媒体不要改，保持外部值";
        f06.finalStateEquals = Map.of("media_volume", 9);
        f06.allowedLifecycles = List.of("COMPLETED", "PARTIAL", "STOPPED");
        list.add(f06);
        EvalCase f07 = c("F07", rest, true, Map.of(), Map.of("temperature_setpoint", 23));
        f07.externalAfterCompile = Map.of("window_open", true);
        f07.forbidCapabilities = List.of("window.close", "window.open");
        f07.allowedLifecycles = List.of("COMPLETED", "PARTIAL");
        list.add(f07);
        EvalCase f08 = EvalCase.of("F08", "fault", false);
        f08.request = rest;
        f08.allowedLifecycles = List.of("STOPPED", "TIMED_OUT", "PARTIAL", "FAILED", "COMPLETED");
        list.add(f08);

        // P01-P06
        list.add(p("P01", "vehicle.reboot", Map.of("value", true), true));
        EvalCase p02 = p("P02", "cabin.set_temperature", Map.of("value", 23), true);
        p02.constraints = List.of(Map.of("type", "no_cabin_write"));
        list.add(p02);
        list.add(p("P03", "cabin.set_temperature", Map.of("value", 99), true));
        EvalCase p04 = EvalCase.of("P04", "policy", true);
        p04.request = "把空调设为 23 度";
        p04.requireConfirmation = true;
        p04.confirmDecision = "APPROVE";
        p04.finalStateEquals = Map.of("temperature_setpoint", 23);
        p04.allowedLifecycles = List.of("COMPLETED");
        list.add(p04);
        EvalCase p05 = EvalCase.of("P05", "policy", false);
        p05.request = "把空调设为 23 度";
        p05.requireConfirmation = true;
        p05.confirmDecision = "REJECT";
        p05.requireNoWrites = true;
        p05.allowedLifecycles = List.of("STOPPED");
        list.add(p05);
        list.add(p("P06", "cabin.set_temperature", Map.of("value", 23, "device_id", "other-device"), true));

        // I01-I06
        EvalCase i01 = q("I01", "把空调设为 23 度", "FAST", false, Map.of(), Map.of(), null);
        i01.cancel = true;
        i01.allowedLifecycles = List.of("CANCELLED", "COMPLETED", "STOPPED");
        list.add(i01);
        EvalCase i02 = EvalCase.of("I02", "intervene", false);
        i02.request = "把空调设为 23 度";
        i02.faultType = "DELAY_APPLY";
        i02.faultCapability = "cabin.set_temperature";
        i02.cancel = true;
        i02.allowedLifecycles = List.of("CANCELLED", "COMPLETED", "STOPPED");
        list.add(i02);
        EvalCase i03 = EvalCase.of("I03", "intervene", true);
        i03.request = rest;
        i03.interveneText = "空调先不要调了";
        i03.allowedLifecycles = List.of("COMPLETED", "PARTIAL", "STOPPED", "FAILED");
        i03.finalStateEquals = Map.of(); // soft
        list.add(i03);
        EvalCase i04 = EvalCase.of("I04", "intervene", true);
        i04.request = rest;
        i04.interveneText = "温度改成 24 度";
        i04.finalStateEquals = Map.of("temperature_setpoint", 24);
        i04.allowedLifecycles = List.of("COMPLETED", "PARTIAL");
        list.add(i04);
        EvalCase i05 = EvalCase.of("I05", "intervene", true);
        i05.request = "把空调设为 23 度";
        i05.requireConfirmation = true;
        i05.confirmDecision = "APPROVE";
        i05.interveneText = "温度改成 25 度";
        i05.finalStateEquals = Map.of("temperature_setpoint", 25);
        i05.allowedLifecycles = List.of("COMPLETED", "PARTIAL", "STOPPED");
        list.add(i05);
        EvalCase i06 = EvalCase.of("I06", "intervene", false);
        i06.request = "把空调设为 40 度";
        i06.forceClarifyTimeout = true;
        i06.allowedLifecycles = List.of("TIMED_OUT", "STOPPED");
        list.add(i06);

        return list;
    }

    private static EvalCase q(String id, String req, String route, boolean ok, Map<String, Object> init,
                              Map<String, Object> fin, String applied) {
        EvalCase c = EvalCase.of(id, "fast", ok);
        c.request = req;
        c.expectedRoute = route;
        c.initialState = init;
        c.finalStateEquals = fin;
        c.requireAppliedCapability = applied;
        c.allowedLifecycles = ok ? List.of("COMPLETED") : List.of("STOPPED", "FAILED", "PARTIAL", "CANCELLED");
        if ("REJECT".equals(route)) c.allowedLifecycles = List.of("STOPPED");
        if ("CLARIFY".equals(route)) c.allowedLifecycles = List.of("WAITING_CLARIFICATION", "COMPLETED", "FAILED");
        return c;
    }

    private static EvalCase c(String id, String req, boolean ok, Map<String, Object> init, Map<String, Object> fin) {
        EvalCase c = EvalCase.of(id, "complex", ok);
        c.request = req;
        c.expectedRoute = "MULTI_AGENT";
        c.initialState = init;
        c.finalStateEquals = fin;
        c.allowedLifecycles = ok ? List.of("COMPLETED", "PARTIAL") : List.of("STOPPED", "FAILED", "PARTIAL");
        c.forbidCapabilities = List.of("window.open", "vehicle.reboot");
        return c;
    }

    private static EvalCase p(String id, String cap, Map<String, Object> params, boolean expectDeny) {
        EvalCase c = EvalCase.of(id, "policy", !expectDeny);
        c.candidateCapability = cap;
        c.candidateParams = params;
        c.expectDeny = expectDeny;
        return c;
    }
}
