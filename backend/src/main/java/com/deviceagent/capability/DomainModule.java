package com.deviceagent.capability;

/**
 * Pluggable terminal/domain capability pack.
 * Harness + Agent stay fixed; new domains register tools here instead of rewriting Runtime.
 */
public interface DomainModule {
    /** Stable module id, e.g. {@code terminal} or {@code iot}. */
    String id();

    void register(CapabilityRegistrar registrar);
}
