package com.deviceagent.device;

/** Adapter-neutral fault injection kinds for local/dev DevicePort implementations. */
public enum FaultType {
    NONE,
    REJECT,
    ACK_NOT_APPLIED,
    APPLIED_RESPONSE_LOST,
    DELAY_APPLY,
    TOOL_TIMEOUT,
    READ_FAIL,
    STALE_STATE
}
