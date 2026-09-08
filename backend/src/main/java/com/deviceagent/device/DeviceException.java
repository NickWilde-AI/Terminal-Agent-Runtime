package com.deviceagent.device;

/** Adapter-neutral device error. Simulator and future vehicle adapters share this type. */
public class DeviceException extends RuntimeException {
    private final String code;
    private final String actionId;

    public DeviceException(String code, String message) {
        this(code, message, null);
    }

    public DeviceException(String code, String message, String actionId) {
        super(message);
        this.code = code;
        this.actionId = actionId;
    }

    public String getCode() {
        return code;
    }

    public String getActionId() {
        return actionId;
    }
}
