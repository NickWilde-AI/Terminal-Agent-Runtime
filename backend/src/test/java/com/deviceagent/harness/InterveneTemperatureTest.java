package com.deviceagent.harness;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class InterveneTemperatureTest {
    @Test
    void parsesVariousTemps() {
        assertEquals(25, HarnessService.extractInterveneTemperature("温度改成 25 度"));
        assertEquals(27, HarnessService.extractInterveneTemperature("空调设为27"));
        assertEquals(22, HarnessService.extractInterveneTemperature("改成 22度"));
        assertNull(HarnessService.extractInterveneTemperature("随便说说"));
        assertThrows(IllegalArgumentException.class,
                () -> HarnessService.extractInterveneTemperature("温度改成 99 度"));
    }
}
