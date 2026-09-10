package com.deviceagent.capability;

import java.util.*;

/** Product predicates, independent of model-written criteria and eval expected answers. */
public final class CapabilityEffects {
    private CapabilityEffects() {}

    public static Map<String, Object> expected(String id, Map<String, Object> p) {
        Object v = p.get("value");
        return switch (id) {
            case "climate.set_power" -> Map.of("climate_power", v);
            case "climate.set_temperature", "cabin.set_temperature" -> Map.of("temperature_setpoint", v);
            case "climate.set_fan", "cabin.set_fan" -> Map.of("fan_level", v);
            case "window.set_position" -> {
                Map<String, Object> m = new LinkedHashMap<>();
                for (String w : CapabilityRegistry.WINDOWS) {
                    if ("all".equals(p.get("window")) || w.equals(p.get("window"))) {
                        m.put("window_" + w, p.get("position"));
                    }
                }
                yield m;
            }
            case "media.play" -> Map.of("media_playing", true, "media_artist", p.get("artist"));
            case "media.pause" -> Map.of("media_playing", false);
            case "media.set_volume" -> Map.of("media_volume", v);
            case "navigation.start", "navigation.set_route" -> Map.of(
                    "navigation_active", true,
                    "navigation_destination", p.get("destination"),
                    "navigation_paused", false);
            case "navigation.stop", "navigation.exit", "navigation.nav_exit" -> Map.of(
                    "navigation_active", false,
                    "navigation_paused", false);
            case "navigation.pause" -> Map.of("navigation_paused", true);
            case "navigation.resume" -> Map.of("navigation_paused", false);
            case "navigation.set_preference" -> Map.of("navigation_preference", v);
            case "navigation.navigate_home" -> Map.of("navigation_active", true, "navigation_paused", false);
            case "navigation.navigate_company" -> Map.of("navigation_active", true, "navigation_paused", false);
            case "navigation.set_home" -> Map.of("navigation_home", p.get("place"));
            case "navigation.set_company" -> Map.of("navigation_company", p.get("place"));
            case "navigation.set_prompt_enabled" -> Map.of("prompt_enabled", v);
            case "navigation.set_volume" -> Map.of("navigation_volume", v);
            case "navigation.set_muted" -> Map.of("navigation_muted", v);
            case "life.search_shops" -> Map.of("life_session_active", true, "life_phase", "shop_list");
            case "life.enter_shop" -> Map.of("life_session_active", true, "life_phase", "in_shop");
            case "life.add_to_cart" -> Map.of("life_session_active", true, "life_phase", "in_shop");
            case "life.go_to_checkout" -> Map.of("life_session_active", true, "life_phase", "checkout");
            case "life.close" -> Map.of("life_session_active", false, "life_phase", "idle");
            // query / waypoint list mutations are resolved in the simulator (state-dependent)
            default -> Map.of();
        };
    }

    public static boolean eq(Object a, Object b) {
        return a instanceof Number x && b instanceof Number y
                ? x.doubleValue() == y.doubleValue()
                : Objects.equals(a, b);
    }

    public static boolean matches(String id, Map<String, Object> p, Map<String, Object> state) {
        var expected = expected(id, p);
        if (expected.isEmpty()) {
            return switch (id) {
                case "navigation.add_waypoint" -> {
                    Object waypoints = state.get("navigation_waypoints");
                    yield waypoints instanceof List<?> list && list.contains(p.get("name"));
                }
                case "navigation.remove_waypoint" -> {
                    Object waypoints = state.get("navigation_waypoints");
                    yield waypoints instanceof List<?> list && !list.contains(p.get("name"));
                }
                case "navigation.query_eta", "navigation.query_status", "navigation.query_waypoints" ->
                        Objects.equals(state.get("last_nav_query_type"), switch (id) {
                            case "navigation.query_eta" -> "eta";
                            case "navigation.query_status" -> "status";
                            default -> "waypoints";
                        });
                default -> false;
            };
        }
        return expected.entrySet().stream().allMatch(e -> eq(state.get(e.getKey()), e.getValue()));
    }
}
