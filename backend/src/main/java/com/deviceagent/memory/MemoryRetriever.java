package com.deviceagent.memory;

import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Retrieve + relevance/TTL filter + conflict arbitration (recency > confidence > frequency).
 */
@Component
public class MemoryRetriever {
    private static final Duration TTL = Duration.ofDays(180);
    private static final int MAX_INJECT = 5;

    private final MemoryStore store;

    public MemoryRetriever(MemoryStore store) {
        this.store = store;
    }

    public List<MemoryEntry> retrieve(String sessionId, String userText, List<Map<String, Object>> goals) {
        List<MemoryEntry> active = store.listActive(sessionId);
        Set<String> goalDomains = inferDomains(userText, goals);
        Instant now = Instant.now();

        List<MemoryEntry> filtered = active.stream()
                .filter(m -> m.getCreatedAt() == null || Duration.between(m.getCreatedAt(), now).compareTo(TTL) <= 0)
                .filter(m -> goalDomains.isEmpty() || goalDomains.contains(m.getDomain()) || "general".equals(m.getDomain()))
                .filter(m -> isRelevant(m, userText, goals))
                .collect(Collectors.toCollection(ArrayList::new));

        Map<String, List<MemoryEntry>> byKey = filtered.stream()
                .collect(Collectors.groupingBy(MemoryEntry::getKey, LinkedHashMap::new, Collectors.toList()));
        List<MemoryEntry> winners = new ArrayList<>();
        for (List<MemoryEntry> group : byKey.values()) {
            winners.add(arbitrate(group));
        }
        winners.sort(Comparator.comparing((MemoryEntry m) -> score(m, now)).reversed());
        if (winners.size() > MAX_INJECT) {
            return winners.subList(0, MAX_INJECT);
        }
        return winners;
    }

    public MemoryEntry arbitrate(List<MemoryEntry> candidates) {
        return candidates.stream()
                .max(Comparator
                        .comparing((MemoryEntry m) -> m.getCreatedAt() == null ? Instant.EPOCH : m.getCreatedAt())
                        .thenComparingDouble(MemoryEntry::getConfidence)
                        .thenComparingInt(MemoryEntry::getHitCount))
                .orElseThrow();
    }

    private double score(MemoryEntry m, Instant now) {
        long ageHours = m.getCreatedAt() == null ? 0
                : Math.max(0, Duration.between(m.getCreatedAt(), now).toHours());
        double recency = 1.0 / (1.0 + ageHours / 24.0);
        return recency * 2.0 + m.getConfidence() + Math.min(1.0, m.getHitCount() / 10.0);
    }

    private boolean isRelevant(MemoryEntry m, String userText, List<Map<String, Object>> goals) {
        String text = userText == null ? "" : userText;
        if ("address_name".equals(m.getKey())) {
            return true;
        }
        if ("cabin_temperature".equals(m.getKey()) || "cabin_fan".equals(m.getKey())) {
            return text.contains("温度") || text.contains("空调") || text.contains("风量")
                    || text.contains("休息") || text.contains("舒服")
                    || goalsContain(goals, "cabin");
        }
        if ("media_volume".equals(m.getKey())) {
            return text.contains("媒体") || text.contains("音量") || text.contains("声音")
                    || text.contains("休息") || text.contains("舒服")
                    || goalsContain(goals, "media");
        }
        return goalDomainsFromText(text).contains(m.getDomain()) || "general".equals(m.getDomain());
    }

    private boolean goalsContain(List<Map<String, Object>> goals, String prefix) {
        if (goals == null) return false;
        return goals.stream().anyMatch(g -> String.valueOf(g.get("type")).startsWith(prefix));
    }

    private Set<String> inferDomains(String userText, List<Map<String, Object>> goals) {
        Set<String> domains = goalDomainsFromText(userText);
        if (goals != null) {
            for (Map<String, Object> g : goals) {
                String type = String.valueOf(g.get("type"));
                if (type.startsWith("cabin")) domains.add("cabin");
                if (type.startsWith("media")) domains.add("media");
                if (type.startsWith("nav")) domains.add("navigation");
            }
        }
        return domains;
    }

    private Set<String> goalDomainsFromText(String text) {
        String t = text == null ? "" : text.toLowerCase(Locale.ROOT);
        Set<String> set = new HashSet<>();
        if (t.contains("温度") || t.contains("空调") || t.contains("风量") || t.contains("休息") || t.contains("舒服")) {
            set.add("cabin");
        }
        if (t.contains("媒体") || t.contains("音量") || t.contains("声音") || t.contains("休息") || t.contains("舒服")) {
            set.add("media");
        }
        if (t.contains("导航")) {
            set.add("navigation");
        }
        if (set.isEmpty()) {
            set.add("cabin");
            set.add("media");
            set.add("general");
        }
        return set;
    }
}
