package com.deviceagent.memory;

import com.deviceagent.config.DeviceAgentProperties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MemoryGateAndRetrieveTest {
    private MemoryService memoryService;
    private MemoryRetriever retriever;

    @BeforeEach
    void setUp() throws Exception {
        DeviceAgentProperties props = new DeviceAgentProperties();
        props.setPersistence("memory"); // in-memory fallback
        MemoryStore store = new MemoryStore(props);
        store.init();
        MemoryWriteGate gate = new MemoryWriteGate();
        retriever = new MemoryRetriever(store);
        ContextBuilder builder = new ContextBuilder(retriever);
        memoryService = new MemoryService(store, gate, retriever, builder);
    }

    @Test
    void explicitPreferenceWritesAndIsAuditable() {
        Map<String, Object> r = memoryService.tryWriteFromUtterance(
                "记住我喜欢温度24度", "web", "run-1");
        assertTrue(Boolean.TRUE.equals(r.get("accepted")));
        @SuppressWarnings("unchecked")
        Map<String, Object> mem = (Map<String, Object>) r.get("memory");
        assertEquals("cabin_temperature", mem.get("key"));
        assertEquals("24", mem.get("value"));
        assertEquals("run-1", mem.get("source_run_id"));
    }

    @Test
    void privacyGateBlocksSensitive() {
        Map<String, Object> r = memoryService.tryWriteFromUtterance(
                "记住我的银行卡密码是123456", "web", "run-2");
        assertFalse(Boolean.TRUE.equals(r.get("accepted")));
        assertEquals("privacy_blocked", r.get("reason"));
    }

    @Test
    void conflictArbitrationPrefersNewerHigherConfidence() {
        memoryService.tryWriteFromUtterance("记住温度23度", "web", "run-a");
        memoryService.tryWriteFromUtterance("记住温度25度", "web", "run-b");
        List<MemoryEntry> hits = retriever.retrieve("web", "后排要休息调舒服一点", List.of());
        assertFalse(hits.isEmpty());
        MemoryEntry temp = hits.stream().filter(m -> "cabin_temperature".equals(m.getKey())).findFirst().orElseThrow();
        assertEquals("25", temp.getValue());
    }

    @Test
    void irrelevantMemoryNotInjectedForNavOnly() {
        memoryService.tryWriteFromUtterance("记住温度22度", "web", "run-c");
        List<MemoryEntry> hits = retriever.retrieve("web", "导航有画面但没有声音", List.of(
                Map.of("type", "nav_muted", "value", false)
        ));
        assertTrue(hits.stream().noneMatch(m -> "cabin_temperature".equals(m.getKey())));
    }

    @Test
    void missingSourceRejectedOnUtteranceWrite() {
        Map<String, Object> r = memoryService.tryWriteFromUtterance("记住我喜欢温度24度", "web", null);
        assertFalse(Boolean.TRUE.equals(r.get("accepted")));
        assertEquals("missing_source", r.get("reason"));
    }

    @Test
    void missingSourceRejectedOnManualWrite() {
        MemoryEntry e = new MemoryEntry();
        e.setKey("cabin_temperature");
        e.setValue("23");
        e.setDomain("cabin");
        e.setCategory("preference");
        e.setSessionId("web");
        Map<String, Object> r = memoryService.writeManual(e);
        assertFalse(Boolean.TRUE.equals(r.get("accepted")));
        assertEquals("missing_source", r.get("reason"));
    }
}
