package com.deviceagent.capability;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * Shared capability schema for Tool Calling, Policy and DevicePort adapters.
 * Domains register through {@link DomainModule}; Harness/Agent do not hardcode domain packs.
 */
@Component
public class CapabilityRegistry {
    public static final String VERSION = "capabilities-v4";
    /** @deprecated use {@link TerminalDomainModule#WINDOWS} */
    public static final List<String> WINDOWS = TerminalDomainModule.WINDOWS;
    /** @deprecated use {@link TerminalDomainModule#ROUTE_PREFERENCES} */
    public static final List<String> ROUTE_PREFERENCES = TerminalDomainModule.ROUTE_PREFERENCES;

    private final Map<String, CapabilityDefinition> capabilities = new LinkedHashMap<>();
    private final List<String> moduleIds = new ArrayList<>();

    public CapabilityRegistry() {
        this(defaultModules());
    }

    public CapabilityRegistry(List<DomainModule> modules) {
        CapabilityRegistrar registrar = new CapabilityRegistrar() {
            @Override
            public void add(String id, String description, boolean write, String domain, Map<String, Object> properties) {
                capabilities.put(id, new CapabilityDefinition(
                        id, VERSION, description, write, Set.of(domain),
                        Map.of("type", "object",
                                "properties", properties,
                                "required", new ArrayList<>(properties.keySet()),
                                "additionalProperties", false)));
            }

            @Override
            public void alias(String alias, String canonicalId) {
                CapabilityDefinition def = capabilities.get(canonicalId);
                if (def == null) {
                    throw new IllegalArgumentException("alias target missing: " + canonicalId);
                }
                capabilities.put(alias, def);
            }
        };
        for (DomainModule module : modules) {
            module.register(registrar);
            moduleIds.add(module.id());
        }
    }

    public static List<DomainModule> defaultModules() {
        return List.of(new TerminalDomainModule(), new IotDomainModule());
    }

    public List<String> moduleIds() {
        return List.copyOf(moduleIds);
    }

    public Optional<CapabilityDefinition> get(String id) {
        return Optional.ofNullable(capabilities.get(id));
    }

    public Collection<CapabilityDefinition> all() {
        return new LinkedHashSet<>(capabilities.values());
    }

    public String canonical(String id) {
        return get(id).map(CapabilityDefinition::getId).orElse(id);
    }

    public List<Map<String, Object>> tools() {
        return all().stream()
                .map(c -> Map.<String, Object>of(
                        "type", "function",
                        "function", Map.of(
                                "name", wireName(c.getId()),
                                "description", c.getDescription(),
                                "parameters", c.getSchema())))
                .toList();
    }

    public static String wireName(String id) {
        return id.replace('.', '_');
    }

    public String fromWire(String name) {
        return all().stream().map(CapabilityDefinition::getId)
                .filter(id -> wireName(id).equals(name))
                .findFirst()
                .orElse(name);
    }

    @SuppressWarnings("unchecked")
    public ValidationResult validate(String id, Map<String, Object> params) {
        var d = capabilities.get(id);
        if (d == null) return ValidationResult.deny("UNKNOWN_CAPABILITY", "未注册能力: " + id);
        if (params == null) return ValidationResult.deny("SCHEMA", "参数必须是对象");
        Map<String, Object> props = (Map<String, Object>) d.getSchema().get("properties");
        if (!params.keySet().equals(props.keySet())) {
            return ValidationResult.deny("SCHEMA", "参数字段必须为 " + props.keySet());
        }
        for (var e : props.entrySet()) {
            Map<String, Object> s = (Map<String, Object>) e.getValue();
            Object v = params.get(e.getKey());
            String t = (String) s.get("type");
            boolean ok = switch (t) {
                case "integer" -> v instanceof Number n && Double.isFinite(n.doubleValue())
                        && n.doubleValue() == n.intValue()
                        && n.intValue() >= (int) s.get("minimum")
                        && n.intValue() <= (int) s.get("maximum");
                case "boolean" -> v instanceof Boolean;
                case "string" -> v instanceof String x && !x.isBlank()
                        && x.length() <= ((Number) s.getOrDefault("maxLength", 120)).intValue()
                        && (!s.containsKey("enum") || ((List<?>) s.get("enum")).contains(x));
                default -> false;
            };
            if (!ok) return ValidationResult.deny("SCHEMA", "非法参数: " + e.getKey() + "，不截断执行");
        }
        return ValidationResult.ok(d);
    }

    public record ValidationResult(boolean ok, String code, String message, CapabilityDefinition definition) {
        public static ValidationResult ok(CapabilityDefinition d) {
            return new ValidationResult(true, null, null, d);
        }

        public static ValidationResult deny(String c, String m) {
            return new ValidationResult(false, c, m, null);
        }
    }
}
