package com.deviceagent.simulator;

import com.deviceagent.device.DeviceException;

public class SimulatorException extends DeviceException {
    public SimulatorException(String code, String message) {
        super(code, message);
    }

    public SimulatorException(String code, String message, String actionId) {
        super(code, message, actionId);
    }
}
