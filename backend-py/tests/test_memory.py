"""Memory write-gate and retrieval semantics."""

from __future__ import annotations

from terminal_agent.config import Settings
from terminal_agent.memory.context_builder import ContextBuilder
from terminal_agent.memory.retriever import MemoryRetriever
from terminal_agent.memory.service import MemoryService
from terminal_agent.memory.store import MemoryStore
from terminal_agent.memory.write_gate import MemoryWriteGate


def _svc() -> MemoryService:
    settings = Settings(persistence="memory", sqlite_path="./data/mem-test.db")
    store = MemoryStore(settings)
    store.init()
    gate = MemoryWriteGate()
    retriever = MemoryRetriever(store)
    return MemoryService(store, gate, retriever, ContextBuilder(retriever))


def test_explicit_preference_accepted() -> None:
    svc = _svc()
    out = svc.try_write_from_utterance("记住以后温度23度", "web", "run-1")
    assert out["accepted"] is True
    assert out["memory"]["key"] == "cabin_temperature"
    assert out["memory"]["value"] == "23"


def test_privacy_blocked() -> None:
    svc = _svc()
    out = svc.try_write_from_utterance("记住密码是123456", "web", "run-1")
    assert out["accepted"] is False
    assert out["reason"] == "privacy_blocked"


def test_missing_source_rejected() -> None:
    svc = _svc()
    out = svc.try_write_from_utterance("记住以后温度23度", "web", None)
    assert out["accepted"] is False
    assert out["reason"] == "missing_source"


def test_navigation_does_not_inject_cabin_memory() -> None:
    svc = _svc()
    svc.try_write_from_utterance("记住以后温度23度", "web", "run-1")
    memories = svc.retriever().retrieve("web", "导航到东方明珠", [])
    assert all(m.key != "cabin_temperature" for m in memories)
