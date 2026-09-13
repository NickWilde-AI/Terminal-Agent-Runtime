"""Minimal context injection for each model decision (docs/03 §14.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from terminal_agent.contracts import StateSnapshot
from terminal_agent.memory.entry import MemoryEntry
from terminal_agent.memory.retriever import MemoryRetriever


@dataclass(frozen=True)
class BuiltContext:
    payload: dict[str, Any]
    memories: list[MemoryEntry]
    hints: list[dict[str, Any]]
    approx_tokens: int


class ContextBuilder:
    def __init__(self, retriever: MemoryRetriever) -> None:
        self.retriever = retriever

    def build(
        self,
        session_id: str | None,
        user_text: str | None,
        goals: list[dict[str, Any]] | None,
        constraints: list[dict[str, Any]] | None,
        criteria: list[dict[str, Any]] | None,
        observation: StateSnapshot | None,
        prior_actions: list[dict[str, Any]] | None,
        tenant_id: str | None = None,
    ) -> BuiltContext:
        memories = self.retriever.retrieve(session_id, user_text, goals, tenant_id)
        hints = [m.to_hint() for m in memories]
        payload: dict[str, Any] = {
            "goals": goals or [],
            "constraints": constraints or [],
            "criteria": criteria or [],
            "observation": observation.state if observation is not None else {},
            "prior_actions_summary": self._summarize_actions(prior_actions),
            "long_term_memory": hints,
            "token_budget_note": "minimal_context_v1",
        }
        approx_tokens = self._estimate_tokens(payload)
        payload["approx_tokens"] = approx_tokens
        return BuiltContext(payload, memories, hints, approx_tokens)

    def build_for_compile(
        self,
        session_id: str | None,
        user_text: str | None,
        observation: StateSnapshot | None,
        tenant_id: str | None = None,
    ) -> BuiltContext:
        return self.build(session_id, user_text, [], [], [], observation, [], tenant_id)

    @staticmethod
    def _summarize_actions(prior_actions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if not prior_actions:
            return []
        start = max(0, len(prior_actions) - 6)
        out: list[dict[str, Any]] = []
        for action in prior_actions[start:]:
            out.append(
                {
                    "capability_id": action.get("capability_id"),
                    "execution_status": action.get("execution_status"),
                    "params": action.get("params"),
                }
            )
        return out

    @staticmethod
    def _estimate_tokens(payload: dict[str, Any]) -> int:
        return max(1, len(str(payload)) // 3)
