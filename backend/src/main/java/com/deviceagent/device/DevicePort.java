package com.deviceagent.device;

import com.deviceagent.domain.DeviceDomain;
import com.deviceagent.domain.StateSnapshot;

import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.function.Consumer;

/**
 * Device adapter boundary. Harness, Policy and Verifier depend on this port,
 * not on a specific simulator or terminal SDK.
 *
 * Core invariant: Harness + Agent remain the execution center; domains plug in
 * through Capability + DevicePort, without rewriting the main loop.
 */
public interface DevicePort {
    String getDeviceId();

    String getEnvironmentId();

    StateSnapshot readState(Set<DeviceDomain> domains);

    StateSnapshot snapshot();

    Map<String, Object> view();

    ActionRecord applyWrite(
            String actionId,
            String idempotencyKey,
            String capabilityId,
            Map<String, Object> params,
            String environmentId,
            Instant deadline,
            Map<String, Long> expectedRevisions,
            String runId,
            int goalVersion
    );

    ActionRecord queryAction(String actionId);

    void resetToDefaults();

    void forceNewEnvironment();

    void injectFault(FaultType type, String capabilityId, int times);

    void clearFault();

    void applyInitialState(Map<String, Object> fields);

    void externalChange(String field, Object value);

    void addChangeListener(Consumer<Map<String, Object>> listener);

    void onPersist(Consumer<Map<String, Object>> sink);
}
