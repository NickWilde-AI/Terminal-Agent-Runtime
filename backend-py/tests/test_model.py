from __future__ import annotations

import json
from types import SimpleNamespace

import httpx

from terminal_agent.agent.contracts import CompiledTaskCandidate
from terminal_agent.capability.registry import CapabilityRegistry
from terminal_agent.domain.models import StateSnapshot
from terminal_agent.model.normalizer import ModelOutputNormalizer
from terminal_agent.model.openai_compatible import OpenAiCompatibleModelAdapter


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        model_base_url="https://model.invalid/v1",
        model_api_key="secret",
        model_id="test-model",
        model_edge_id="edge-model",
        model_placement="cloud",
        model_timeout_ms=1000,
    )


def test_remaps_temperature_param_alias() -> None:
    out = ModelOutputNormalizer.normalize_action(
        {"capability_id": "cabin.set_temperature", "params": {"temperature": 23}}
    )
    assert out["params"]["value"] == 23


def test_forces_multi_agent_for_complex_or_multi_goal() -> None:
    candidate = CompiledTaskCandidate(
        route_hint="FAST",
        goals=[{"type": "cabin_temperature", "value": 23}],
        fast_action={"capability_id": "cabin.set_temperature", "params": {"value": 23}},
    )
    ModelOutputNormalizer.normalize(candidate, "休息一下，调舒服点，不要开窗，保留导航提示")
    assert candidate.route_hint == "MULTI_AGENT"
    assert candidate.raw["route_corrected"] == "complex_request_force_multi_agent"

    candidate = CompiledTaskCandidate(route_hint="FAST", goals=[
        {"type": "cabin_temperature", "value": 23},
        {"type": "cabin_fan", "value": 1},
    ])
    ModelOutputNormalizer.normalize(candidate, "设温度和风量")
    assert candidate.route_hint == "MULTI_AGENT"
    assert len(candidate.criteria) >= 2


def test_keeps_fast_for_simple_set() -> None:
    candidate = CompiledTaskCandidate(
        route_hint="FAST", goals=[{"type": "cabin_temperature", "value": 23}]
    )
    ModelOutputNormalizer.normalize(candidate, "把空调设为 23 度")
    assert candidate.route_hint == "FAST"


def test_tools_follow_goals_and_constraints(monkeypatch) -> None:
    # Isolate this contract from TaskBinder implementation timing.
    from terminal_agent.runtime.task_binder import TaskBinder

    monkeypatch.setattr(TaskBinder, "action_for", staticmethod(
        lambda goal: {"capability_id": "climate.set_temperature", "params": {"value": goal["value"]}}
    ))
    adapter = OpenAiCompatibleModelAdapter(settings(), registry=CapabilityRegistry())
    names = [tool["function"]["name"] for tool in adapter.tools_for_task(
        [{"type": "cabin_temperature", "value": 23}], [{"type": "no_window"}]
    )]
    assert "device_get_state" in names
    assert "climate_set_temperature" in names
    assert not any(name.startswith("window_") for name in names)
    assert "media_play" not in names


def test_standard_tool_call_and_role_tool_feedback(monkeypatch) -> None:
    from terminal_agent.runtime.task_binder import TaskBinder

    monkeypatch.setattr(TaskBinder, "action_for", staticmethod(
        lambda _: {"capability_id": "climate.set_temperature", "params": {"value": 23}}
    ))
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "type": "function", "function": {
                "name": "climate_set_temperature", "arguments": '{"value":23}'
            }}],
        }}]})

    adapter = OpenAiCompatibleModelAdapter(
        settings(), registry=CapabilityRegistry(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    adapter.request_context("run-1", 1, None)
    plan = adapter.plan_next(
        "run-1", [{"type": "cabin_temperature", "value": 23}], [],
        [], StateSnapshot(state={"temperature_setpoint": 26}), [], [],
    )
    assert "tools" in captured[0]
    assert plan["tool_call_id"] == "call_1"
    assert adapter.sessions["run-1"].messages[-1]["tool_calls"][0]["type"] == "function"

    adapter.feedback("run-1", 1, plan, {"status": "APPLIED"})
    tool_message = adapter.sessions["run-1"].messages[-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_1"
    assert tool_message["name"] == "climate_set_temperature"
