package com.deviceagent.capability;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class CapabilityDefinition {
    private final String id;
    private final String version;
    private final String description;
    private final boolean write;
    private final Set<String> domains;
    private final Map<String, Object> schema;

    public CapabilityDefinition(String id, String version, String description, boolean write,
                                Set<String> domains, Map<String, Object> schema) {
        this.id = id;
        this.version = version;
        this.description = description;
        this.write = write;
        this.domains = domains;
        this.schema = schema;
    }

    public String getId() { return id; }
    public String getVersion() { return version; }
    public String getDescription() { return description; }
    public boolean isWrite() { return write; }
    public Set<String> getDomains() { return domains; }
    public Map<String, Object> getSchema() { return schema; }

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("capability_id", id);
        m.put("version", version);
        m.put("description", description);
        m.put("write", write);
        m.put("domains", domains);
        m.put("schema", schema);
        return m;
    }
}
