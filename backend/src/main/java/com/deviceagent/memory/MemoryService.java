package com.deviceagent.memory;

import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class MemoryService {
    private final MemoryStore store;
    private final MemoryWriteGate writeGate;
    private final MemoryRetriever retriever;
    private final ContextBuilder contextBuilder;

    public MemoryService(
            MemoryStore store,
            MemoryWriteGate writeGate,
            MemoryRetriever retriever,
            ContextBuilder contextBuilder
    ) {
        this.store = store;
        this.writeGate = writeGate;
        this.retriever = retriever;
        this.contextBuilder = contextBuilder;
    }

    public ContextBuilder contextBuilder() {
        return contextBuilder;
    }

    public MemoryRetriever retriever() {
        return retriever;
    }

    public List<MemoryEntry> list(String sessionId) {
        return store.listActive(sessionId);
    }

    public Map<String, Object> tryWriteFromUtterance(String utterance, String sessionId, String sourceRunId) {
        MemoryWriteGate.GateResult result = writeGate.tryExtractExplicit(utterance, sessionId, sourceRunId);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("accepted", result.accepted());
        out.put("reason", result.reason());
        if (!result.accepted()) {
            return out;
        }
        MemoryEntry saved = store.save(result.candidate());
        out.put("memory", saved.toMap());
        return out;
    }

    public Map<String, Object> writeManual(MemoryEntry entry) {
        Map<String, Object> out = new LinkedHashMap<>();
        if (entry.getSourceRunId() == null || entry.getSourceRunId().isBlank()) {
            out.put("accepted", false);
            out.put("reason", "missing_source");
            return out;
        }
        if (writeGate.isSensitive(entry.getValue()) || writeGate.isSensitive(entry.getKey())) {
            out.put("accepted", false);
            out.put("reason", "privacy_blocked");
            return out;
        }
        if (!writeGate.allowedKeys().contains(entry.getKey())) {
            out.put("accepted", false);
            out.put("reason", "unsupported_key");
            return out;
        }
        MemoryEntry saved = store.save(entry);
        out.put("accepted", true);
        out.put("reason", "manual");
        out.put("memory", saved.toMap());
        return out;
    }

    public boolean delete(String id) {
        return store.softDelete(id);
    }

    public void markHits(List<MemoryEntry> memories) {
        if (memories == null) return;
        for (MemoryEntry m : memories) {
            store.markHit(m.getId());
        }
    }

    public void clearSession(String sessionId) {
        store.clearSession(sessionId);
    }

    public List<Map<String, Object>> asHints(List<MemoryEntry> memories) {
        return memories.stream().map(MemoryEntry::toHint).toList();
    }
}
