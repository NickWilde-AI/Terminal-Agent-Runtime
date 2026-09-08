package com.deviceagent.domain;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class Ids {
    private Ids() {}

    public static String newId(String prefix) {
        return prefix + "_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }

    public static Instant now() {
        return Instant.now();
    }

    public static Map<String, Object> mapOf(Object... kv) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i + 1 < kv.length; i += 2) {
            map.put(String.valueOf(kv[i]), kv[i + 1]);
        }
        return map;
    }

    /** Like Map.of but allows null values (Map.of throws NPE on null). */
    public static Map<String, Object> dict(Object... kv) {
        return mapOf(kv);
    }

    public static List<String> copyList(List<String> in) {
        return in == null ? new ArrayList<>() : new ArrayList<>(in);
    }
}
