package com.deviceagent.model;

import com.deviceagent.config.DeviceAgentProperties;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicLong;

/**
 * Cloud / Edge model placement.
 * Same ModelPort contract; switching placement bumps epoch so late cloud plans are discarded.
 * Edge is a protocol stub — not a real NPU Step Edge deployment.
 */
@Component
public class ModelRouter {
    private final DeviceAgentProperties properties;
    private final AtomicLong epoch = new AtomicLong(1);

    public ModelRouter(DeviceAgentProperties properties) {
        this.properties = properties;
    }

    public long epoch() {
        return epoch.get();
    }

    public String activeModelId() {
        DeviceAgentProperties.ModelProps m = properties.getModel();
        if ("edge".equalsIgnoreCase(m.getPlacement())) {
            String edge = m.getEdgeModelId();
            return edge == null || edge.isBlank() ? "step-edge-stub" : edge;
        }
        return m.getModelId();
    }

    public String placement() {
        String p = properties.getModel().getPlacement();
        return p == null || p.isBlank() ? "cloud" : p.toLowerCase();
    }

    public boolean isOfflineEdge() {
        return "edge".equalsIgnoreCase(placement());
    }

    public void setPlacement(String placement) {
        String next = placement == null ? "cloud" : placement.toLowerCase();
        String prev = this.placement();
        properties.getModel().setPlacement(next);
        if (!prev.equals(next)) {
            epoch.incrementAndGet();
        }
    }
}
