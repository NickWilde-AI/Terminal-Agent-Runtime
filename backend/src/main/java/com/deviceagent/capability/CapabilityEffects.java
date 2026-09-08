package com.deviceagent.capability;
import java.util.*;

/** Product predicates, independent of model-written criteria and eval expected answers. */
public final class CapabilityEffects {
    private CapabilityEffects() {}
    public static Map<String,Object> expected(String id,Map<String,Object> p) {
        Object v=p.get("value");
        return switch(id) {
            case "climate.set_power" -> Map.of("climate_power",v);
            case "climate.set_temperature", "cabin.set_temperature" -> Map.of("temperature_setpoint",v);
            case "climate.set_fan", "cabin.set_fan" -> Map.of("fan_level",v);
            case "window.set_position" -> {
                Map<String,Object> m=new LinkedHashMap<>();
                for(String w:CapabilityRegistry.WINDOWS) if("all".equals(p.get("window")) || w.equals(p.get("window"))) m.put("window_"+w,p.get("position"));
                yield m;
            }
            case "media.play" -> Map.of("media_playing",true,"media_artist",p.get("artist"));
            case "media.pause" -> Map.of("media_playing",false);
            case "media.set_volume" -> Map.of("media_volume",v);
            case "navigation.start" -> Map.of("navigation_active",true,"navigation_destination",p.get("destination"));
            case "navigation.stop" -> Map.of("navigation_active",false);
            case "navigation.set_prompt_enabled" -> Map.of("prompt_enabled",v);
            case "navigation.set_volume" -> Map.of("navigation_volume",v);
            case "navigation.set_muted" -> Map.of("navigation_muted",v);
            default -> Map.of();
        };
    }
    public static boolean eq(Object a,Object b) { return a instanceof Number x && b instanceof Number y ? x.doubleValue()==y.doubleValue() : Objects.equals(a,b); }
    public static boolean matches(String id,Map<String,Object> p,Map<String,Object> state) {
        var expected=expected(id,p); return !expected.isEmpty() && expected.entrySet().stream().allMatch(e -> eq(state.get(e.getKey()),e.getValue()));
    }
}
