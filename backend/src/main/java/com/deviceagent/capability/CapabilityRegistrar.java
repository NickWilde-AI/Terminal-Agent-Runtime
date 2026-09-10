package com.deviceagent.capability;

import java.util.Map;

/** Used by DomainModule implementations to register capabilities into the shared registry. */
public interface CapabilityRegistrar {
    void add(String id, String description, boolean write, String domain, Map<String, Object> properties);

    void alias(String alias, String canonicalId);
}
