"""Application dependency graph — Spring-style wiring for FastAPI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from terminal_agent.capability.core import CapabilityRegistry
from terminal_agent.config import Settings, get_settings
from terminal_agent.device.simulator import DeviceSimulator
from terminal_agent.memory.context_builder import ContextBuilder
from terminal_agent.memory.retriever import MemoryRetriever
from terminal_agent.memory.service import MemoryService
from terminal_agent.memory.store import MemoryStore
from terminal_agent.memory.write_gate import MemoryWriteGate
from terminal_agent.model.fake import FakeModelAdapter
from terminal_agent.model.openai_compatible import OpenAiCompatibleModelAdapter
from terminal_agent.model.router import ModelRouter as SettingsModelRouter
from terminal_agent.persistence.sqlite import SqlitePersistence
from terminal_agent.persistence.store import InMemoryRunStore
from terminal_agent.policy.engine import PolicyEngine
from terminal_agent.runtime.baseline import BaselineRunner
from terminal_agent.runtime.executor import CapabilityExecutor
from terminal_agent.runtime.harness import HarnessService
from terminal_agent.runtime.support import ModelRouter, RuntimeSettings, TaskBinder, BudgetSettings
from terminal_agent.runtime.verifier import Verifier


@dataclass
class AppState:
    settings: Settings
    registry: CapabilityRegistry
    simulator: DeviceSimulator
    store: InMemoryRunStore
    policy: PolicyEngine
    executor: CapabilityExecutor
    verifier: Verifier
    persistence: SqlitePersistence
    memory_store: MemoryStore
    memory: MemoryService
    model: Any
    model_router: ModelRouter
    settings_model_router: SettingsModelRouter
    harness: HarnessService
    baseline: BaselineRunner
    eval_runner: Any | None = None
    sse_hub: Any | None = field(default=None, repr=False)


def build_runtime_settings(settings: Settings) -> RuntimeSettings:
    return RuntimeSettings(
        defaults_rule_id=settings.defaults_rule_id,
        fresh_window_ms=settings.fresh_window_ms,
        budget=BudgetSettings(
            absolute_deadline_seconds=settings.absolute_deadline_seconds,
            max_model_calls=settings.max_model_calls,
            max_tool_calls=settings.max_tool_calls,
            max_write_actions=settings.max_write_actions,
            max_replans=settings.max_replans,
            max_same_failure=settings.max_same_failure,
        ),
    )


def build_model(settings: Settings, registry: CapabilityRegistry) -> tuple[Any, ModelRouter, SettingsModelRouter]:
    support_router = ModelRouter(
        model_id=settings.model_id,
        edge_model_id=settings.model_edge_id,
        placement=settings.model_placement,
    )
    settings_router = SettingsModelRouter(settings)
    mode = (settings.model_mode or "openai_compatible").lower()
    if mode == "fake":
        return FakeModelAdapter(), support_router, settings_router
    model = OpenAiCompatibleModelAdapter(settings, model_router=settings_router, registry=None)
    # OpenAI adapter expects capability.registry.CapabilityRegistry; pass None and let it
    # construct its own, or pass core via a thin shim — adapter defaults to CapabilityRegistry().
    return model, support_router, settings_router


def set_model_placement(state: AppState, placement: str) -> None:
    state.model_router.set_placement(placement)
    state.settings_model_router.set_placement(placement)
    state.settings.model_placement = placement.lower()


def set_require_confirmation(state: AppState, enabled: bool) -> None:
    state.settings.require_confirmation = enabled
    state.policy.require_confirmation = enabled


def build_app_state(settings: Settings | None = None) -> AppState:
    settings = settings or get_settings()
    settings.ensure_dirs()

    registry = CapabilityRegistry()
    simulator = DeviceSimulator(registry)
    store = InMemoryRunStore(settings.event_log_dir)
    policy = PolicyEngine(registry, settings.require_confirmation)
    executor = CapabilityExecutor(simulator, registry, policy, store)
    verifier = Verifier(simulator)
    persistence = SqlitePersistence(
        store,
        simulator,
        settings.sqlite_path,
        enabled=str(settings.persistence).lower() == "sqlite",
    )

    memory_store = MemoryStore(settings)
    write_gate = MemoryWriteGate()
    retriever = MemoryRetriever(memory_store)
    context_builder = ContextBuilder(retriever)
    memory = MemoryService(memory_store, write_gate, retriever, context_builder)

    model, model_router, settings_model_router = build_model(settings, registry)
    runtime_settings = build_runtime_settings(settings)
    binder = TaskBinder(registry)

    harness = HarnessService(
        store,
        simulator,
        model,
        binder,
        executor,
        verifier,
        persistence,
        runtime_settings,
        memory=memory,
        router=model_router,
    )
    baseline = BaselineRunner(
        store, simulator, model, binder, executor, verifier, persistence, runtime_settings
    )

    eval_runner = None
    try:
        from terminal_agent.eval.runner import EvalRunner

        eval_runner = EvalRunner(
            harness,
            simulator,
            store,
            policy,
            registry,
            model,
            baseline,
            settings,
        )
    except Exception:  # noqa: BLE001 — parent may still be landing EvalRunner
        eval_runner = None

    return AppState(
        settings=settings,
        registry=registry,
        simulator=simulator,
        store=store,
        policy=policy,
        executor=executor,
        verifier=verifier,
        persistence=persistence,
        memory_store=memory_store,
        memory=memory,
        model=model,
        model_router=model_router,
        settings_model_router=settings_model_router,
        harness=harness,
        baseline=baseline,
        eval_runner=eval_runner,
    )


def capability_to_map(definition: Any) -> dict[str, Any]:
    return {
        "capability_id": definition.id,
        "version": CapabilityRegistry.VERSION,
        "description": getattr(definition, "description", "") or "",
        "write": definition.write,
        "domains": sorted(definition.domains),
        "schema": {
            "type": "object",
            "properties": definition.properties,
            "required": list(definition.properties.keys()),
            "additionalProperties": False,
        },
    }


def list_capabilities(registry: CapabilityRegistry) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for definition in registry.capabilities.values():
        if definition.id in seen:
            continue
        seen.add(definition.id)
        out.append(capability_to_map(definition))
    return out
