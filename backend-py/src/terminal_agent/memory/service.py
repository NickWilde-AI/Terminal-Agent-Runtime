"""Memory facade used by harness (hints) and HTTP API."""

from __future__ import annotations

import builtins
from typing import Any

from terminal_agent.contracts import StateSnapshot
from terminal_agent.memory.context_builder import ContextBuilder
from terminal_agent.memory.entry import MemoryEntry
from terminal_agent.memory.retriever import MemoryRetriever
from terminal_agent.memory.store import MemoryStore
from terminal_agent.memory.write_gate import MemoryWriteGate


class MemoryService:
    def __init__(
        self,
        store: MemoryStore,
        write_gate: MemoryWriteGate,
        retriever: MemoryRetriever,
        context_builder: ContextBuilder,
    ) -> None:
        self.store = store
        self.write_gate = write_gate
        self._retriever = retriever
        self._context_builder = context_builder

    def context_builder(self) -> ContextBuilder:
        return self._context_builder

    def retriever(self) -> MemoryRetriever:
        return self._retriever

    def list(self, session_id: str | None) -> builtins.list[MemoryEntry]:
        return self.store.list_active(session_id)

    def try_write_from_utterance(
        self, utterance: str | None, session_id: str | None, source_run_id: str | None
    ) -> dict[str, Any]:
        result = self.write_gate.try_extract_explicit(utterance, session_id, source_run_id)
        out: dict[str, Any] = {"accepted": result.accepted, "reason": result.reason}
        if not result.accepted or result.candidate is None:
            return out
        saved = self.store.save(result.candidate)
        out["memory"] = saved.to_map()
        return out

    def write_manual(self, entry: MemoryEntry) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if entry.source_run_id is None or not str(entry.source_run_id).strip():
            out["accepted"] = False
            out["reason"] = "missing_source"
            return out
        if self.write_gate.is_sensitive(entry.value) or self.write_gate.is_sensitive(entry.key):
            out["accepted"] = False
            out["reason"] = "privacy_blocked"
            return out
        if entry.key not in self.write_gate.allowed_keys():
            out["accepted"] = False
            out["reason"] = "unsupported_key"
            return out
        saved = self.store.save(entry)
        out["accepted"] = True
        out["reason"] = "manual"
        out["memory"] = saved.to_map()
        return out

    def delete(self, id_: str) -> bool:
        return self.store.soft_delete(id_)

    def mark_hits(self, memories: builtins.list[MemoryEntry] | None) -> None:
        if memories is None:
            return
        for entry in memories:
            if entry.id:
                self.store.mark_hit(entry.id)

    def clear_session(self, session_id: str | None) -> None:
        self.store.clear_session(session_id)

    def as_hints(self, memories: builtins.list[MemoryEntry]) -> builtins.list[dict[str, Any]]:
        return [m.to_hint() for m in memories]

    # --- Harness NullMemory-compatible adapters ---

    async def compile_hints(
        self, session_id: str, text: str, snapshot: StateSnapshot
    ) -> builtins.list[dict[str, Any]]:
        ctx = self._context_builder.build_for_compile(session_id, text, snapshot)
        return ctx.hints

    async def plan_hints(
        self,
        session_id: str,
        text: str | None,
        goals: builtins.list[dict[str, Any]],
        constraints: builtins.list[dict[str, Any]],
        snapshot: StateSnapshot,
        prior: builtins.list[dict[str, Any]],
    ) -> builtins.list[dict[str, Any]]:
        ctx = self._context_builder.build(
            session_id, text, goals, constraints, [], snapshot, prior
        )
        return ctx.hints
