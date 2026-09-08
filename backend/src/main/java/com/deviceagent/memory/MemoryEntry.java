package com.deviceagent.memory;

import com.deviceagent.domain.Ids;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Controlled long-term memory entry (docs/03 §14).
 * Affects defaults/suggestions only; never bypasses Policy.
 */
public class MemoryEntry {
    private String id;
    private String sessionId = "local";
    private String category; // preference | experience
    private String key;
    private String value;
    private String domain; // cabin | media | navigation | general
    private String sourceRunId;
    private Instant createdAt = Ids.now();
    private double confidence = 1.0;
    private int hitCount;
    private Instant lastHitAt;
    private boolean active = true;
    private String note;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }
    public String getKey() { return key; }
    public void setKey(String key) { this.key = key; }
    public String getValue() { return value; }
    public void setValue(String value) { this.value = value; }
    public String getDomain() { return domain; }
    public void setDomain(String domain) { this.domain = domain; }
    public String getSourceRunId() { return sourceRunId; }
    public void setSourceRunId(String sourceRunId) { this.sourceRunId = sourceRunId; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
    public double getConfidence() { return confidence; }
    public void setConfidence(double confidence) { this.confidence = confidence; }
    public int getHitCount() { return hitCount; }
    public void setHitCount(int hitCount) { this.hitCount = hitCount; }
    public Instant getLastHitAt() { return lastHitAt; }
    public void setLastHitAt(Instant lastHitAt) { this.lastHitAt = lastHitAt; }
    public boolean isActive() { return active; }
    public void setActive(boolean active) { this.active = active; }
    public String getNote() { return note; }
    public void setNote(String note) { this.note = note; }

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", id);
        m.put("session_id", sessionId);
        m.put("category", category);
        m.put("key", key);
        m.put("value", value);
        m.put("domain", domain);
        m.put("source_run_id", sourceRunId);
        m.put("created_at", createdAt == null ? null : createdAt.toString());
        m.put("confidence", confidence);
        m.put("hit_count", hitCount);
        m.put("last_hit_at", lastHitAt == null ? null : lastHitAt.toString());
        m.put("active", active);
        m.put("note", note);
        return m;
    }

    public Map<String, Object> toHint() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", id);
        m.put("category", category);
        m.put("key", key);
        m.put("value", value);
        m.put("domain", domain);
        m.put("confidence", confidence);
        m.put("source_run_id", sourceRunId);
        return m;
    }
}
