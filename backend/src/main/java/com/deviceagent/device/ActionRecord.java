package com.deviceagent.device;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/** Adapter-neutral write/query result returned by DevicePort. */
public class ActionRecord {
    public String actionId;
    public String idempotencyKey;
    public String capabilityId;
    public String environmentId;
    public String runId;
    public String status;
    public String message;
    public int goalVersion;
    public Map<String, Object> params = new LinkedHashMap<>();
    public Map<String, Long> expectedRevisions = new LinkedHashMap<>();
    public Instant createdAt;
    public Instant finishedAt;
    public Instant deadline;
    public long applyAfterMs;
    public long revision;
}
