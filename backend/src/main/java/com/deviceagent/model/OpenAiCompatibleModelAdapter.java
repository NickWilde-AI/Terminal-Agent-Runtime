package com.deviceagent.model;

import com.deviceagent.agent.MultiAgentSupport;
import com.deviceagent.agent.PlanDraft;
import com.deviceagent.agent.ReviewResult;
import com.deviceagent.agent.TaskSpec;
import com.deviceagent.capability.CapabilityRegistry;
import com.deviceagent.config.DeviceAgentProperties;
import com.deviceagent.domain.AgentRole;
import com.deviceagent.domain.ReviewDecision;
import com.deviceagent.domain.StateSnapshot;
import com.deviceagent.harness.GoalCompiler;
import com.deviceagent.harness.TaskBinder;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * OpenAI-compatible adapter with standard Tool Calling for planNext.
 * compileTask still uses structured JSON; parse failures never fall back to Fake.
 */
@Component
@ConditionalOnProperty(prefix = "device-agent.model", name = "mode", havingValue = "openai_compatible")
public class OpenAiCompatibleModelAdapter implements ModelPort {

    private final DeviceAgentProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;
    private final ModelRouter modelRouter;
    private final CapabilityRegistry registry;
    private final ConcurrentHashMap<String, Session> sessions = new ConcurrentHashMap<>();

    public OpenAiCompatibleModelAdapter(
            DeviceAgentProperties properties,
            ObjectMapper objectMapper,
            ModelRouter modelRouter,
            CapabilityRegistry registry
    ) {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.modelRouter = modelRouter;
        this.registry = registry;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(properties.getModel().getTimeoutMs()))
                .build();
    }

    @Override
    public String mode() {
        return "openai_compatible";
    }

    @Override
    public void requestContext(String runId, int goalVersion, Instant deadline) {
        Session s = sessions.computeIfAbsent(runId, id -> new Session());
        s.goalVersion = goalVersion;
        s.deadline = deadline;
    }

    @Override
    public void feedback(String runId, int goalVersion, Map<String, Object> plan, Map<String, Object> result) {
        Session s = sessions.computeIfAbsent(runId, id -> new Session());
        if (s.goalVersion != goalVersion) return;
        String toolCallId = String.valueOf(plan.getOrDefault("tool_call_id", "call_" + System.nanoTime()));
        String name = CapabilityRegistry.wireName(String.valueOf(plan.get("capability_id")));
        Map<String, Object> toolMsg = new LinkedHashMap<>();
        toolMsg.put("role", "tool");
        toolMsg.put("tool_call_id", toolCallId);
        toolMsg.put("name", name);
        toolMsg.put("content", safeJson(result));
        s.messages.add(toolMsg);
    }

    @Override
    public CompiledTaskCandidate compileTask(
            String userText,
            StateSnapshot observation,
            List<Map<String, Object>> memoryHints
    ) {
        ensureConfigured();
        String system = """
                你是智能终端主 Agent（MAIN）。只输出 JSON，不要输出其它文字。
                JSON 字段：routeHint(CHAT|FAST|MULTI_AGENT|CLARIFY|REJECT), clarifyQuestion, rejectReason, summary,
                goals([{type,value,window?,position?,artist?,destination?}]), constraints([{type}]),
                criteria([{template_id,params,required,source}]), fastAction({capability_id,params})。
                硬性约定：
                1) 写动作 params：value 型用 {"value":...}；window.set_position 用 {"window","position"}；
                   media.play 用 {"artist"}；navigation.start 用 {"destination"}；
                   navigation.add_waypoint/remove_waypoint 用 {"name"}；pause/stop/home/company/query_* 用 {}。
                2) goals.type：climate_power, cabin_temperature, cabin_fan, window_position, media_play,
                   media_pause, media_volume, nav_start, nav_stop, nav_home, nav_company, nav_add_waypoint,
                   nav_remove_waypoint, nav_preference, nav_pause, nav_resume, nav_query_eta, nav_query_status,
                   nav_query_waypoints, nav_prompt_enabled, nav_volume, nav_muted。
                3) 纯聊天 → CHAT（summary 写回复）；多目标/多域/约束/途经 → MULTI_AGENT；单一明确写 → FAST；信息不足 → CLARIFY。
                4) 「不要开窗」是约束 no_window，不是拒绝开窗能力；用户明确开窗且无禁止约束时必须绑定 window_position。
                5) 用户提到的每个显式子目标都必须进入 goals，禁止只编译温度而丢掉车窗/播放/导航。
                6) 导航原则：明确目的地直接开航；途经不丢终点；search 失败诚实；「回家/去公司」若含途经/顺路则拆成收藏开航+途经，禁止只走收藏抢跑。
                允许能力：climate.*, window.set_position, media.*, navigation.*（含途经/偏好/收藏/查询）, life.*（仅接口）, iot.light.set_power（第二域样例）,
                device.get_state。
                """;
        String user = "用户原话：" + userText
                + "\n当前观察：" + safeJson(observation == null ? Map.of() : observation.getState())
                + "\n长期记忆偏好：" + safeJson(memoryHints == null ? List.of() : memoryHints)
                + "\n检测到的意图：" + safeJson(GoalCompiler.detectIntents(userText, userText))
                + "\nmodel_placement：" + modelRouter.placement();
        String content = chatText(system, user);
        try {
            CompiledTaskCandidate parsed = parseCompile(content, userText);
            ModelOutputNormalizer.normalize(parsed, userText);
            GoalCompiler.ensureCoverage(parsed, GoalCompiler.detectIntents(userText, userText));
            return parsed;
        } catch (Exception ex) {
            throw new IllegalStateException(
                    "模型输出无法解析为合法任务 JSON（不降级 Fake）: " + ex.getMessage()
                            + "; raw=" + truncate(content, 500),
                    ex
            );
        }
    }

    @Override
    public Map<String, Object> planNext(
            String runId,
            List<Map<String, Object>> goals,
            List<Map<String, Object>> constraints,
            List<Map<String, Object>> criteria,
            StateSnapshot observation,
            List<Map<String, Object>> priorActions,
            List<Map<String, Object>> memoryHints
    ) {
        ensureConfigured();
        Session session = sessions.computeIfAbsent(runId, id -> new Session());
        if (session.messages.isEmpty()) {
            session.messages.add(Map.of("role", "system", "content", """
                    你是智能终端执行规划器。通过 function/tool calling 提出下一个候选写动作。
                    一次只调用一个工具。目标已满足时不要调用工具，直接用自然语言说明 FINISH。
                    需要澄清时回复文本 CLARIFY:问题。不要编造未注册工具。
                    长期记忆只作默认建议，不得覆盖本轮目标/约束。
                    """));
        }
        Map<String, Object> userPayload = new LinkedHashMap<>();
        userPayload.put("goals", goals);
        userPayload.put("constraints", constraints);
        userPayload.put("criteria", criteria);
        userPayload.put("observation", observation.getState());
        userPayload.put("priorActions", priorActions);
        userPayload.put("long_term_memory", memoryHints == null ? List.of() : memoryHints);
        session.messages.add(Map.of("role", "user", "content", "请根据以下状态决定下一步：\n" + safeJson(userPayload)));

        ChatResult result = chatWithTools(session.messages, toolsForTask(goals, constraints));
        if (result.toolCalls != null && !result.toolCalls.isEmpty()) {
            Map<String, Object> call = result.toolCalls.getFirst();
            String wire = String.valueOf(call.get("name"));
            String cap = registry.fromWire(wire);
            Map<String, Object> args = parseArgs(call.get("arguments"));
            Map<String, Object> out = ModelOutputNormalizer.normalizeAction(Map.of(
                    "decision", "ACT",
                    "capability_id", cap,
                    "params", args,
                    "tool_call_id", call.get("id"),
                    "reason", "tool_call"
            ));
            // Persist assistant tool_calls turn for subsequent feedback
            Map<String, Object> assistant = new LinkedHashMap<>();
            assistant.put("role", "assistant");
            assistant.put("content", result.content == null ? "" : result.content);
            assistant.put("tool_calls", List.of(Map.of(
                    "id", call.get("id"),
                    "type", "function",
                    "function", Map.of("name", wire, "arguments", safeJson(args))
            )));
            session.messages.add(assistant);
            out.put("model_raw", result.raw);
            return out;
        }
        String content = result.content == null ? "" : result.content.trim();
        session.messages.add(Map.of("role", "assistant", "content", content));
        if (content.toUpperCase().startsWith("CLARIFY")) {
            String q = content.replaceFirst("(?i)^CLARIFY:?\\s*", "").trim();
            return Map.of("decision", "CLARIFY", "question", q.isBlank() ? "请补充目标" : q, "model_raw", result.raw);
        }
        // Try JSON fallback for decision
        try {
            if (content.contains("{")) {
                JsonNode node = objectMapper.readTree(extractJson(content));
                Map<String, Object> out = objectMapper.convertValue(node, Map.class);
                if (out.containsKey("capability_id") || out.containsKey("capabilityId")) {
                    Map<String, Object> normalized = ModelOutputNormalizer.normalizeAction(out);
                    normalized.put("model_raw", result.raw);
                    return normalized;
                }
                if (out.containsKey("decision")) {
                    out.put("model_raw", result.raw);
                    return out;
                }
            }
        } catch (Exception ignored) {
            // fall through to FINISH
        }
        return Map.of("decision", "FINISH", "reason", content.isBlank() ? "模型未提出新动作" : content, "model_raw", result.raw);
    }

    @Override
    public void requestContext(String runId, com.deviceagent.domain.AgentRole role, int goalVersion, Instant deadline) {
        String key = sessionKey(runId, role);
        Session s = sessions.computeIfAbsent(key, id -> new Session());
        s.goalVersion = goalVersion;
        s.deadline = deadline;
        s.role = role;
    }

    @Override
    public PlanDraft planDraft(
            String runId,
            TaskSpec taskSpec,
            StateSnapshot observation,
            List<Map<String, Object>> priorActions,
            List<String> reviseSuggestions,
            int revisionRound
    ) {
        ensureConfigured();
        String key = sessionKey(runId, AgentRole.PLANNER);
        Session session = sessions.computeIfAbsent(key, id -> new Session());
        session.role = AgentRole.PLANNER;
        session.goalVersion = taskSpec.goalVersion;
        if (session.messages.isEmpty()) {
            session.messages.add(Map.of("role", "system", "content", """
                    你是执行规划 Agent（PLANNER）。只输出 JSON PlanDraft，不要直接执行设备。
                    字段：actions([{capability_id,params,reason}]), order([int]), preconditions([]),
                    expected_effects([]), assumptions([string]), unresolved([string])。
                    只能使用 TaskSpec.allowed_capabilities 内的能力；遵守 constraints；不要省略用户目标。
                    """));
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("task_spec", taskSpec.toMap());
        payload.put("observation", observation == null ? Map.of() : observation.getState());
        payload.put("prior_actions", priorActions == null ? List.of() : priorActions);
        payload.put("revise_suggestions", reviseSuggestions == null ? List.of() : reviseSuggestions);
        payload.put("revision_round", revisionRound);
        session.messages.add(Map.of("role", "user", "content", "请生成 PlanDraft JSON：\n" + safeJson(payload)));
        String content = chatTextFromSession(session);
        session.messages.add(Map.of("role", "assistant", "content", content));
        try {
            JsonNode node = objectMapper.readTree(extractJson(content));
            PlanDraft draft = new PlanDraft();
            draft.runId = runId;
            draft.goalVersion = taskSpec.goalVersion;
            draft.modelId = modelRouter.activeModelId();
            draft.revisionRound = revisionRound;
            draft.actions = listOfMaps(node.get("actions"));
            draft.actions = draft.actions.stream().map(ModelOutputNormalizer::normalizeAction).toList();
            if (node.has("order") && node.get("order").isArray()) {
                node.get("order").forEach(n -> draft.order.add(n.asInt()));
            } else {
                for (int i = 0; i < draft.actions.size(); i++) draft.order.add(i);
            }
            draft.preconditions = listOfMaps(node.get("preconditions"));
            draft.expectedEffects = listOfMaps(node.get("expected_effects"));
            draft.assumptions = listOfStrings(node.get("assumptions"));
            draft.unresolved = listOfStrings(node.get("unresolved"));
            draft.raw.put("api_raw", content);
            draft.raw.put("agent_role", "PLANNER");
            return draft;
        } catch (Exception ex) {
            // Safe fallback: deterministic planner so Runtime still has a candidate
            PlanDraft fallback = MultiAgentSupport.buildPlanDraft(
                    taskSpec, observation, priorActions, revisionRound, modelRouter.activeModelId());
            fallback.runId = runId;
            fallback.raw.put("parse_fallback", ex.getMessage());
            return fallback;
        }
    }

    @Override
    public ReviewResult reviewPlan(String runId, TaskSpec taskSpec, PlanDraft draft) {
        ensureConfigured();
        String key = sessionKey(runId, AgentRole.REVIEWER);
        Session session = sessions.computeIfAbsent(key, id -> new Session());
        session.role = AgentRole.REVIEWER;
        session.goalVersion = taskSpec.goalVersion;
        if (session.messages.isEmpty()) {
            session.messages.add(Map.of("role", "system", "content", """
                    你是方案审核 Agent（REVIEWER）。只输出 JSON ReviewResult，不能改设备，也不能宣告 COMPLETED。
                    字段：decision(PASS|REVISE|REJECT), missing_goals([]), violated_constraints([]),
                    risky_actions([]), evidence_gaps([]), suggestions([])。
                    对照 TaskSpec 检查目标遗漏、约束冲突、多做/少做。
                    """));
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("task_spec", taskSpec.toMap());
        payload.put("plan_draft", draft.toMap());
        session.messages.add(Map.of("role", "user", "content", "请审核：\n" + safeJson(payload)));
        String content = chatTextFromSession(session);
        session.messages.add(Map.of("role", "assistant", "content", content));
        try {
            JsonNode node = objectMapper.readTree(extractJson(content));
            ReviewResult result = new ReviewResult();
            result.runId = runId;
            result.goalVersion = taskSpec.goalVersion;
            result.modelId = modelRouter.activeModelId();
            String d = text(node, "decision");
            result.decision = d == null ? ReviewDecision.REJECT : ReviewDecision.valueOf(d.toUpperCase());
            result.missingGoals = listOfStrings(node.get("missing_goals"));
            result.violatedConstraints = listOfStrings(node.get("violated_constraints"));
            result.riskyActions = listOfStrings(node.get("risky_actions"));
            result.evidenceGaps = listOfStrings(node.get("evidence_gaps"));
            result.suggestions = listOfStrings(node.get("suggestions"));
            result.raw.put("api_raw", content);
            result.raw.put("agent_role", "REVIEWER");
            return result;
        } catch (Exception ex) {
            ReviewResult fallback = MultiAgentSupport.review(taskSpec, draft, modelRouter.activeModelId());
            fallback.runId = runId;
            fallback.raw.put("parse_fallback", ex.getMessage());
            return fallback;
        }
    }

    private String sessionKey(String runId, AgentRole role) {
        return runId + "::" + (role == null ? AgentRole.MAIN : role).name();
    }

    private String chatTextFromSession(Session session) {
        ChatResult r = chatWithTools(session.messages, null);
        return r.content == null ? "" : r.content;
    }

    private List<String> listOfStrings(JsonNode node) {
        if (node == null || !node.isArray()) return new ArrayList<>();
        List<String> list = new ArrayList<>();
        node.forEach(n -> list.add(n.asText()));
        return list;
    }

    /** Only current-task capabilities plus state read; constraints can further shrink the whitelist. */
    @SuppressWarnings("unchecked")
    List<Map<String, Object>> toolsForTask(List<Map<String, Object>> goals, List<Map<String, Object>> constraints) {
        Set<String> allowed = new LinkedHashSet<>();
        allowed.add("device.get_state");
        if (goals != null) {
            for (Map<String, Object> g : goals) {
                Map<String, Object> action = TaskBinder.actionFor(g);
                if (action != null) {
                    allowed.add(registry.canonical(String.valueOf(action.get("capability_id"))));
                }
            }
        }
        boolean noCabin = constraints != null && constraints.stream().anyMatch(c -> "no_cabin_write".equals(c.get("type")));
        boolean noWindow = constraints != null && constraints.stream().anyMatch(c -> "no_window".equals(c.get("type")));
        boolean noMedia = constraints != null && constraints.stream().anyMatch(c -> "no_media_write".equals(c.get("type")));
        return registry.tools().stream().filter(tool -> {
            Map<String, Object> fn = (Map<String, Object>) tool.get("function");
            String cap = registry.canonical(registry.fromWire(String.valueOf(fn.get("name"))));
            if (noCabin && cap.startsWith("climate.")) return false;
            if (noWindow && cap.startsWith("window.")) return false;
            if (noMedia && cap.startsWith("media.")) return false;
            return allowed.contains(cap);
        }).toList();
    }

    private CompiledTaskCandidate parseCompile(String content, String userText) throws Exception {
        JsonNode node = objectMapper.readTree(extractJson(content));
        CompiledTaskCandidate c = new CompiledTaskCandidate();
        c.routeHint = text(node, "routeHint");
        c.clarifyQuestion = text(node, "clarifyQuestion");
        c.rejectReason = text(node, "rejectReason");
        c.summary = text(node, "summary");
        c.goals = listOfMaps(node.get("goals"));
        c.constraints = listOfMaps(node.get("constraints"));
        c.criteria = listOfMaps(node.get("criteria"));
        if (node.has("fastAction") && !node.get("fastAction").isNull()) {
            c.fastAction = objectMapper.convertValue(node.get("fastAction"), Map.class);
        }
        c.raw.put("model_mode", "openai_compatible");
        c.raw.put("model_id", modelRouter.activeModelId());
        c.raw.put("model_placement", modelRouter.placement());
        c.raw.put("input", userText);
        c.raw.put("api_raw", content);
        return c;
    }

    private String chatText(String system, String user) {
        List<Map<String, Object>> messages = new ArrayList<>();
        messages.add(Map.of("role", "system", "content", system));
        messages.add(Map.of("role", "user", "content", user));
        ChatResult r = chatWithTools(messages, null);
        return r.content == null ? "" : r.content;
    }

    private ChatResult chatWithTools(List<Map<String, Object>> messages, List<Map<String, Object>> tools) {
        try {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("model", modelRouter.activeModelId());
            body.put("temperature", 0);
            body.put("messages", messages);
            if (tools != null && !tools.isEmpty()) {
                body.put("tools", tools);
                body.put("tool_choice", "auto");
            }
            String base = properties.getModel().getBaseUrl().replaceAll("/$", "");
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(base + "/chat/completions"))
                    .timeout(Duration.ofMillis(properties.getModel().getTimeoutMs()))
                    .header("Content-Type", "application/json")
                    .header("Authorization", "Bearer " + properties.getModel().getApiKey())
                    .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(body)))
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 300) {
                throw new IllegalStateException("模型 API 失败 HTTP " + response.statusCode() + ": " + response.body());
            }
            JsonNode root = objectMapper.readTree(response.body());
            JsonNode message = root.path("choices").path(0).path("message");
            ChatResult result = new ChatResult();
            result.raw = response.body();
            result.content = message.path("content").isMissingNode() || message.path("content").isNull()
                    ? null : message.path("content").asText();
            if (message.has("tool_calls") && message.get("tool_calls").isArray()) {
                result.toolCalls = new ArrayList<>();
                for (JsonNode tc : message.get("tool_calls")) {
                    Map<String, Object> call = new LinkedHashMap<>();
                    call.put("id", tc.path("id").asText("call_" + System.nanoTime()));
                    call.put("name", tc.path("function").path("name").asText());
                    call.put("arguments", tc.path("function").path("arguments").asText("{}"));
                    result.toolCalls.add(call);
                }
            }
            return result;
        } catch (IllegalStateException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException("模型 API 调用失败: " + e.getMessage(), e);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseArgs(Object arguments) {
        try {
            if (arguments instanceof Map<?, ?> m) {
                Map<String, Object> out = new LinkedHashMap<>();
                m.forEach((k, v) -> out.put(String.valueOf(k), v));
                return out;
            }
            String raw = String.valueOf(arguments == null ? "{}" : arguments);
            if (raw.isBlank()) return Map.of();
            return objectMapper.readValue(raw, Map.class);
        } catch (Exception e) {
            return Map.of();
        }
    }

    private void ensureConfigured() {
        if (properties.getModel().getBaseUrl() == null || properties.getModel().getBaseUrl().isBlank()
                || properties.getModel().getApiKey() == null || properties.getModel().getApiKey().isBlank()) {
            throw new IllegalStateException("openai_compatible 模式未配置 DEVICE_AGENT_MODEL_BASE_URL / DEVICE_AGENT_MODEL_API_KEY，不能静默降级为 Fake");
        }
    }

    private String safeJson(Object o) {
        try {
            return objectMapper.writeValueAsString(o);
        } catch (Exception e) {
            return String.valueOf(o);
        }
    }

    private static String extractJson(String content) {
        String t = content.trim();
        int start = t.indexOf('{');
        int end = t.lastIndexOf('}');
        if (start >= 0 && end > start) return t.substring(start, end + 1);
        return t;
    }

    private static String truncate(String s, int max) {
        if (s == null) return "";
        return s.length() <= max ? s : s.substring(0, max) + "...";
    }

    private static String text(JsonNode node, String field) {
        return node.has(field) && !node.get(field).isNull() ? node.get(field).asText() : null;
    }

    private List<Map<String, Object>> listOfMaps(JsonNode node) {
        if (node == null || !node.isArray()) return new ArrayList<>();
        List<Map<String, Object>> list = new ArrayList<>();
        node.forEach(n -> list.add(objectMapper.convertValue(n, Map.class)));
        return list;
    }

    private static final class Session {
        final List<Map<String, Object>> messages = new ArrayList<>();
        int goalVersion;
        Instant deadline;
        AgentRole role = AgentRole.MAIN;
    }

    private static final class ChatResult {
        String content;
        String raw;
        List<Map<String, Object>> toolCalls;
    }
}
