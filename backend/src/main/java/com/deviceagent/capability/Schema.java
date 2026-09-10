package com.deviceagent.capability;

import java.util.Map;

/** Shared JSON-schema fragments for DomainModule registration. */
public final class Schema {
    private Schema() {}

    public static Map<String, Object> integer(int min, int max) {
        return Map.of("type", "integer", "minimum", min, "maximum", max);
    }

    public static Map<String, Object> bool() {
        return Map.of("type", "boolean");
    }

    public static Map<String, Object> str(int max) {
        return Map.of("type", "string", "minLength", 1, "maxLength", max);
    }
}
