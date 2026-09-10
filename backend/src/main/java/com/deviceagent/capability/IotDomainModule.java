package com.deviceagent.capability;

import java.util.Map;

/**
 * Minimal second domain pack — proves Harness/Agent stay fixed while domains plug in.
 * Example: smart-terminal / robot / home IoT light control.
 */
public final class IotDomainModule implements DomainModule {
    @Override
    public String id() {
        return "iot";
    }

    @Override
    public void register(CapabilityRegistrar r) {
        r.add("iot.light.set_power", "设置智能灯开关（第二域样例，证明域可插拔）", true, "IOT",
                Map.of("value", Schema.bool()));
        r.alias("light.set_power", "iot.light.set_power");
    }
}
