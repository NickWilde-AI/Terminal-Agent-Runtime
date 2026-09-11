"""OpenAI-compatible adapter preserving standard tools/tool_calls/tool messages."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

import httpx

from terminal_agent.agent.contracts import CompiledTaskCandidate, PlanDraft, ReviewResult, TaskSpec
from terminal_agent.capability.core import CapabilityRegistry
from terminal_agent.domain.models import AgentRole, ReviewDecision, StateSnapshot
from terminal_agent.model.normalizer import ModelOutputNormalizer
from terminal_agent.model.router import ModelRouter


@dataclass
class _Session:
    messages: list[dict[str, Any]] = field(default_factory=list)
    goal_version: int = 0
    deadline: datetime | None = None
    role: AgentRole = AgentRole.MAIN


class OpenAiCompatibleModelAdapter:
    def __init__(
        self,
        settings: Any,
        model_router: ModelRouter | None = None,
        registry: CapabilityRegistry | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.model_router = model_router or ModelRouter(settings)
        self.registry = registry or CapabilityRegistry()
        timeout = getattr(settings, "model_timeout_ms", 30_000) / 1000
        self.client = client or httpx.AsyncClient(timeout=timeout)
        self.sessions: dict[str, _Session] = {}

    def mode(self) -> str:
        return "openai_compatible"

    async def request_context(
        self,
        run_id: str,
        goal_version: int,
        deadline: datetime | None,
        role: AgentRole = AgentRole.MAIN,
    ) -> None:
        session = self.sessions.setdefault(self._session_key(run_id, role), _Session())
        session.goal_version, session.deadline, session.role = goal_version, deadline, role

    async def feedback(
        self,
        run_id: str,
        goal_version: int,
        plan: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        session = self.sessions.setdefault(run_id, _Session())
        if session.goal_version != goal_version:
            return
        call_id = str(plan.get("tool_call_id", f"call_{time.time_ns()}"))
        # Standard OpenAI tool result turn; do not collapse this into user/assistant JSON.
        session.messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "name": self.registry.wire_name(str(plan["capability_id"])),
            "content": self._json(result),
        })

    async def compile_task(
        self,
        user_text: str,
        observation: StateSnapshot | None,
        memory_hints: list[dict[str, Any]] | None = None,
    ) -> CompiledTaskCandidate:
        self._ensure_configured()
        from terminal_agent.runtime.goal_compiler import GoalCompiler

        system = (
            "你是智能终端主 Agent（MAIN）。只输出 JSON。字段：routeHint(CHAT|FAST|MULTI_AGENT|"
            "CLARIFY|REJECT), clarifyQuestion, rejectReason, summary, goals, constraints, criteria, fastAction。"
            "写动作 params 使用标准能力参数。纯聊天 CHAT；多目标/多域/约束/途经 MULTI_AGENT；"
            "单一明确写 FAST；信息不足 CLARIFY。用户每个显式子目标都必须进入 goals。"
        )
        state = observation.state if observation else {}
        payload = (
            f"用户原话：{user_text}\n当前观察：{self._json(state)}\n"
            f"长期记忆偏好：{self._json(memory_hints or [])}\n"
            f"检测到的意图：{self._json(list(GoalCompiler.detect_intents(user_text, user_text)))}\n"
            f"model_placement：{self.model_router.placement()}"
        )
        content = (await self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": payload}]
        ))["content"] or ""
        try:
            node = json.loads(self._extract_json(content))
            candidate = CompiledTaskCandidate(
                route_hint=node.get("routeHint"), clarify_question=node.get("clarifyQuestion"),
                reject_reason=node.get("rejectReason"), summary=node.get("summary"),
                goals=node.get("goals") or [], constraints=node.get("constraints") or [],
                criteria=node.get("criteria") or [], fast_action=node.get("fastAction"),
                raw={"model_mode": self.mode(), "model_id": self.model_router.active_model_id(),
                     "model_placement": self.model_router.placement(), "input": user_text, "api_raw": content},
            )
            ModelOutputNormalizer.normalize(candidate, user_text)
            GoalCompiler.ensure_coverage(candidate, GoalCompiler.detect_intents(user_text, user_text))
            return candidate
        except Exception as exc:
            raise RuntimeError(f"模型输出无法解析为合法任务 JSON（不降级 Fake）: {exc}; raw={content[:500]}") from exc

    async def plan_next(
        self,
        run_id: str,
        goals: list[dict[str, Any]],
        constraints: list[dict[str, Any]],
        criteria: list[dict[str, Any]],
        observation: StateSnapshot,
        prior_actions: list[dict[str, Any]],
        memory_hints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._ensure_configured()
        session = self.sessions.setdefault(run_id, _Session())
        if not session.messages:
            session.messages.append({"role": "system", "content":
                "你是执行规划器。一次只调用一个工具；目标满足时直接说明 FINISH；需澄清回复 CLARIFY:问题。"})
        data = {"goals": goals, "constraints": constraints, "criteria": criteria,
                "observation": observation.state, "priorActions": prior_actions,
                "long_term_memory": memory_hints or []}
        session.messages.append({"role": "user", "content": "请根据以下状态决定下一步：\n" + self._json(data)})
        response = await self._chat(session.messages, self.tools_for_task(goals, constraints))
        calls = response.get("tool_calls") or []
        if calls:
            call = calls[0]
            wire, args = call["name"], self._parse_args(call.get("arguments"))
            # Preserve the assistant tool_calls turn exactly in standard protocol shape.
            session.messages.append({
                "role": "assistant", "content": response.get("content") or "",
                "tool_calls": [{"id": call["id"], "type": "function",
                                "function": {"name": wire, "arguments": self._json(args)}}],
            })
            out = ModelOutputNormalizer.normalize_action({
                "decision": "ACT", "capability_id": self.registry.from_wire(wire),
                "params": args, "tool_call_id": call["id"], "reason": "tool_call",
            })
            out["model_raw"] = response["raw"]
            return out
        content = (response.get("content") or "").strip()
        session.messages.append({"role": "assistant", "content": content})
        if content.upper().startswith("CLARIFY"):
            question = content.split(":", 1)[-1].strip()
            return {"decision": "CLARIFY", "question": question or "请补充目标", "model_raw": response["raw"]}
        try:
            node = json.loads(self._extract_json(content))
            if "capability_id" in node or "capabilityId" in node:
                node = ModelOutputNormalizer.normalize_action(node)
            if "decision" in node or "capability_id" in node:
                node["model_raw"] = response["raw"]
                return cast(dict[str, Any], node)
        except Exception:
            pass
        return {"decision": "FINISH", "reason": content or "模型未提出新动作", "model_raw": response["raw"]}

    async def plan_draft(
        self,
        run_id: str,
        task_spec: TaskSpec,
        observation: StateSnapshot,
        prior_actions: list[dict[str, Any]],
        revise_suggestions: list[str] | None,
        revision_round: int,
    ) -> PlanDraft:
        self._ensure_configured()
        key = self._session_key(run_id, AgentRole.PLANNER)
        session = self.sessions.setdefault(key, _Session(role=AgentRole.PLANNER))
        if not session.messages:
            session.messages.append({"role": "system", "content":
                "你是 PLANNER。只输出 JSON PlanDraft：actions,order,preconditions,expected_effects,assumptions,unresolved。"})
        payload = {"task_spec": task_spec.model_dump(mode="json"), "observation": observation.state,
                   "prior_actions": prior_actions, "revise_suggestions": revise_suggestions or [],
                   "revision_round": revision_round}
        session.messages.append({"role": "user", "content": "请生成 PlanDraft JSON：\n" + self._json(payload)})
        response = await self._chat(session.messages)
        content = response.get("content") or ""
        session.messages.append({"role": "assistant", "content": content})
        try:
            node = json.loads(self._extract_json(content))
            actions = [ModelOutputNormalizer.normalize_action(a) for a in node.get("actions", [])]
            return PlanDraft(run_id=run_id, goal_version=task_spec.goal_version,
                model_id=self.model_router.active_model_id(), revision_round=revision_round,
                actions=actions, order=node.get("order", list(range(len(actions)))),
                preconditions=node.get("preconditions", []), expected_effects=node.get("expected_effects", []),
                assumptions=node.get("assumptions", []), unresolved=node.get("unresolved", []),
                raw={"api_raw": content, "agent_role": "PLANNER"})
        except Exception as exc:
            from terminal_agent.agent.multi_agent import MultiAgentSupport
            draft = MultiAgentSupport.build_plan_draft(task_spec, observation, prior_actions, revision_round,
                                                        self.model_router.active_model_id())
            draft.run_id = run_id
            draft.raw["parse_fallback"] = str(exc)
            return draft

    async def review_plan(self, run_id: str, task_spec: TaskSpec, draft: PlanDraft) -> ReviewResult:
        self._ensure_configured()
        key = self._session_key(run_id, AgentRole.REVIEWER)
        session = self.sessions.setdefault(key, _Session(role=AgentRole.REVIEWER))
        if not session.messages:
            session.messages.append({"role": "system", "content":
                "你是 REVIEWER。只输出 JSON：decision,missing_goals,violated_constraints,"
                "risky_actions,evidence_gaps,suggestions。"})
        payload = {"task_spec": task_spec.model_dump(mode="json"), "plan_draft": draft.model_dump(mode="json")}
        session.messages.append({"role": "user", "content": "请审核：\n" + self._json(payload)})
        response = await self._chat(session.messages)
        content = response.get("content") or ""
        session.messages.append({"role": "assistant", "content": content})
        try:
            node = json.loads(self._extract_json(content))
            return ReviewResult(run_id=run_id, goal_version=task_spec.goal_version,
                model_id=self.model_router.active_model_id(),
                decision=ReviewDecision(str(node.get("decision", "REJECT")).upper()),
                missing_goals=node.get("missing_goals", []),
                violated_constraints=node.get("violated_constraints", []),
                risky_actions=node.get("risky_actions", []), evidence_gaps=node.get("evidence_gaps", []),
                suggestions=node.get("suggestions", []), raw={"api_raw": content, "agent_role": "REVIEWER"})
        except Exception as exc:
            from terminal_agent.agent.multi_agent import MultiAgentSupport
            result = MultiAgentSupport.review(task_spec, draft, self.model_router.active_model_id())
            result.run_id = run_id
            result.raw["parse_fallback"] = str(exc)
            return result

    def tools_for_task(
        self, goals: list[dict[str, Any]] | None, constraints: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        from terminal_agent.runtime.support import TaskBinder

        allowed = {"device.get_state"}
        for goal in goals or []:
            if action := TaskBinder.action_for(goal):
                allowed.add(self.registry.canonical(str(action["capability_id"])))
        kinds = {str(c.get("type")) for c in constraints or []}
        result = []
        for tool in self.registry.tools():
            wire = str(tool["function"]["name"])
            capability = self.registry.canonical(self.registry.from_wire(wire))
            if "no_cabin_write" in kinds and capability.startswith("climate."):
                continue
            if "no_window" in kinds and capability.startswith("window."):
                continue
            if "no_media_write" in kinds and capability.startswith("media."):
                continue
            if capability in allowed:
                result.append(tool)
        return result

    async def _chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model_router.active_model_id(), "temperature": 0,
                                "messages": messages}
        if tools:
            body.update(tools=tools, tool_choice="auto")
        base = str(getattr(self.settings, "model_base_url", "")).rstrip("/")
        key = str(getattr(self.settings, "model_api_key", ""))
        response = await self.client.post(
            f"{base}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        if response.status_code >= 300:
            raise RuntimeError(f"模型 API 失败 HTTP {response.status_code}: {response.text}")
        root = response.json()
        message = root["choices"][0]["message"]
        calls = []
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function") or {}
            calls.append({"id": tool_call.get("id", f"call_{time.time_ns()}"),
                          "name": function.get("name", ""), "arguments": function.get("arguments", "{}")})
        return {"content": message.get("content"), "tool_calls": calls, "raw": response.text}

    def _ensure_configured(self) -> None:
        if not getattr(self.settings, "model_base_url", "") or not getattr(self.settings, "model_api_key", ""):
            raise RuntimeError("openai_compatible 模式未配置 DEVICE_AGENT_MODEL_BASE_URL / "
                               "DEVICE_AGENT_MODEL_API_KEY，不能静默降级为 Fake")

    @staticmethod
    def _parse_args(arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return dict(arguments)
        try:
            parsed = json.loads(str(arguments or "{}"))
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _extract_json(content: str) -> str:
        start, end = content.find("{"), content.rfind("}")
        return content[start:end + 1] if start >= 0 and end > start else content.strip()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))

    @staticmethod
    def _session_key(run_id: str, role: AgentRole) -> str:
        # Legacy single-step planner uses the bare run id, matching Java's
        # requestContext(runId, goalVersion, deadline) overload.
        return run_id if role == AgentRole.MAIN else f"{run_id}::{role.value}"
