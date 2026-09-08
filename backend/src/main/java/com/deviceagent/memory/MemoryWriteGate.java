package com.deviceagent.memory;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Write gating for long-term memory: explicit preference, schema, privacy, source required.
 */
@Component
public class MemoryWriteGate {
    private static final Pattern EXPLICIT_TEMP = Pattern.compile(
            "(?:记住|以后|默认).{0,12}(?:温度|空调).{0,8}?(\\d{1,2})\\s*度?");
    private static final Pattern EXPLICIT_FAN = Pattern.compile(
            "(?:记住|以后|默认).{0,12}风量.{0,8}?(\\d)");
    private static final Pattern EXPLICIT_MEDIA = Pattern.compile(
            "(?:记住|以后|默认).{0,12}(?:媒体|音量).{0,8}?(\\d{1,2})");
    private static final Pattern EXPLICIT_NAME = Pattern.compile(
            "(?:记住|叫我|称呼).{0,6}([\\u4e00-\\u9fa5A-Za-z]{1,12})");

    private static final List<String> SENSITIVE = List.of(
            "身份证", "银行卡", "密码", "支付", "手机号", "信用卡", "cvv", "住址", "车牌"
    );

    public record GateResult(boolean accepted, String reason, MemoryEntry candidate) {}

    public GateResult tryExtractExplicit(String utterance, String sessionId, String sourceRunId) {
        if (utterance == null || utterance.isBlank()) {
            return reject("empty");
        }
        if (isSensitive(utterance)) {
            return reject("privacy_blocked");
        }
        Optional<MemoryEntry> temp = matchTemp(utterance);
        if (temp.isPresent()) {
            return accept(temp.get(), sessionId, sourceRunId, "explicit_preference");
        }
        Optional<MemoryEntry> fan = matchFan(utterance);
        if (fan.isPresent()) {
            return accept(fan.get(), sessionId, sourceRunId, "explicit_preference");
        }
        Optional<MemoryEntry> media = matchMedia(utterance);
        if (media.isPresent()) {
            return accept(media.get(), sessionId, sourceRunId, "explicit_preference");
        }
        Optional<MemoryEntry> name = matchName(utterance);
        if (name.isPresent()) {
            return accept(name.get(), sessionId, sourceRunId, "explicit_preference");
        }
        return reject("no_explicit_preference");
    }

    /** Repeated consistent preference across runs (≥N) may be proposed; caller supplies count. */
    public GateResult tryFromRepeated(String key, String value, String domain, int consistentCount,
                                      String sessionId, String sourceRunId) {
        if (consistentCount < 2) {
            return reject("need_repeat_consistency");
        }
        if (sourceRunId == null || sourceRunId.isBlank()) {
            return reject("missing_source");
        }
        if (isSensitive(value)) {
            return reject("privacy_blocked");
        }
        MemoryEntry e = new MemoryEntry();
        e.setCategory("preference");
        e.setKey(key);
        e.setValue(value);
        e.setDomain(domain);
        e.setConfidence(Math.min(0.95, 0.6 + 0.1 * consistentCount));
        e.setNote("repeated_consistency");
        return accept(e, sessionId, sourceRunId, "repeated_consistency");
    }

    public boolean isSensitive(String text) {
        if (text == null) return false;
        String t = text.toLowerCase(Locale.ROOT);
        for (String s : SENSITIVE) {
            if (t.contains(s.toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        // crude phone / id patterns
        return text.matches(".*\\d{11}.*") || text.matches(".*\\d{15,18}.*");
    }

    private Optional<MemoryEntry> matchTemp(String text) {
        Matcher m = EXPLICIT_TEMP.matcher(text);
        if (!m.find()) return Optional.empty();
        int v = Integer.parseInt(m.group(1));
        if (v < 16 || v > 30) return Optional.empty();
        MemoryEntry e = new MemoryEntry();
        e.setCategory("preference");
        e.setKey("cabin_temperature");
        e.setValue(String.valueOf(v));
        e.setDomain("cabin");
        e.setConfidence(0.95);
        return Optional.of(e);
    }

    private Optional<MemoryEntry> matchFan(String text) {
        Matcher m = EXPLICIT_FAN.matcher(text);
        if (!m.find()) return Optional.empty();
        int v = Integer.parseInt(m.group(1));
        if (v < 0 || v > 7) return Optional.empty();
        MemoryEntry e = new MemoryEntry();
        e.setCategory("preference");
        e.setKey("cabin_fan");
        e.setValue(String.valueOf(v));
        e.setDomain("cabin");
        e.setConfidence(0.9);
        return Optional.of(e);
    }

    private Optional<MemoryEntry> matchMedia(String text) {
        Matcher m = EXPLICIT_MEDIA.matcher(text);
        if (!m.find()) return Optional.empty();
        int v = Integer.parseInt(m.group(1));
        if (v < 0 || v > 40) return Optional.empty();
        MemoryEntry e = new MemoryEntry();
        e.setCategory("preference");
        e.setKey("media_volume");
        e.setValue(String.valueOf(v));
        e.setDomain("media");
        e.setConfidence(0.85);
        return Optional.of(e);
    }

    private Optional<MemoryEntry> matchName(String text) {
        if (!text.contains("记住") && !text.contains("叫我") && !text.contains("称呼")) {
            return Optional.empty();
        }
        Matcher m = EXPLICIT_NAME.matcher(text);
        if (!m.find()) return Optional.empty();
        String name = m.group(1);
        if (List.of("温度", "空调", "风量", "媒体", "音量", "导航").contains(name)) {
            return Optional.empty();
        }
        MemoryEntry e = new MemoryEntry();
        e.setCategory("preference");
        e.setKey("address_name");
        e.setValue(name);
        e.setDomain("general");
        e.setConfidence(0.8);
        return Optional.of(e);
    }

    private GateResult accept(MemoryEntry e, String sessionId, String sourceRunId, String reason) {
        if (sourceRunId == null || sourceRunId.isBlank()) {
            return reject("missing_source");
        }
        e.setSessionId(sessionId == null ? "local" : sessionId);
        e.setSourceRunId(sourceRunId);
        return new GateResult(true, reason, e);
    }

    private GateResult reject(String reason) {
        return new GateResult(false, reason, null);
    }

    public List<String> allowedKeys() {
        List<String> keys = new ArrayList<>();
        keys.add("cabin_temperature");
        keys.add("cabin_fan");
        keys.add("media_volume");
        keys.add("address_name");
        return keys;
    }
}
