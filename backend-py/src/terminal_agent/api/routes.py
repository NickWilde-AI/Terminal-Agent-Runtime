"""HTTP API — behavioral port of Java ApiController."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from terminal_agent.api.deps import AppState, list_capabilities, set_model_placement, set_require_confirmation
from terminal_agent.device.port import FaultType
from terminal_agent.memory.entry import MemoryEntry

router = APIRouter(prefix="/api/v1")


def _state(request: Request) -> AppState:
    return request.app.state.app_state


class CreateRunRequest(BaseModel):
    text: str = Field(min_length=1)
    requestId: str | None = None
    sessionId: str | None = None


class ClarifyRequest(BaseModel):
    answer: str = Field(min_length=1)


class InterveneRequest(BaseModel):
    type: str = Field(min_length=1)
    text: str | None = None
    expectedGoalVersion: int | None = None


class AnswerRequest(BaseModel):
    pendingId: str = Field(min_length=1)
    goalVersion: int
    decision: str = Field(min_length=1)
    answer: str | None = None


class FaultRequest(BaseModel):
    type: str = Field(min_length=1)
    capabilityId: str | None = None
    times: int | None = None


class ExternalChangeRequest(BaseModel):
    field: str = Field(min_length=1)
    value: Any = None


class MemoryWriteRequest(BaseModel):
    utterance: str | None = None
    sessionId: str | None = None
    sourceRunId: str | None = None
    category: str | None = None
    key: str | None = None
    value: str | None = None
    domain: str | None = None
    confidence: float | None = None


@router.post("/runs")
async def create_run(req: CreateRunRequest, request: Request) -> dict[str, Any]:
    state = _state(request)
    try:
        run = await state.harness.create_run(req.requestId, req.text, req.sessionId, False)
        return state.harness.to_view(run)
    except RuntimeError as ex:
        raise HTTPException(status_code=409, detail=str(ex)) from ex
    except Exception as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex


@router.get("/runs")
async def list_runs(request: Request) -> dict[str, Any]:
    state = _state(request)
    return {"runs": [state.harness.to_view(r) for r in state.harness.list_runs()]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    state = _state(request)
    run = state.store.find(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return state.harness.to_view(run)


@router.get("/runs/{run_id}/events")
async def events(run_id: str, request: Request, afterSeq: int = Query(0)) -> dict[str, Any]:
    state = _state(request)
    if state.store.find(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    events_ = state.store.events_after(run_id, afterSeq)
    return {
        "run_id": run_id,
        "events": events_,
        "latest_seq": afterSeq if not events_ else events_[-1].seq,
    }


@router.get("/runs/{run_id}/events/stream")
async def stream_events(run_id: str, request: Request, afterSeq: int = Query(0)) -> Any:
    state = _state(request)
    if state.store.find(run_id) is None:
        raise HTTPException(status_code=404, detail="run not found")
    assert state.sse_hub is not None
    return state.sse_hub.subscribe_run(run_id, afterSeq)


@router.get("/device/state/stream")
async def stream_device(request: Request) -> Any:
    state = _state(request)
    assert state.sse_hub is not None
    return state.sse_hub.subscribe_device()


@router.get("/runs/{run_id}/replay")
async def replay(run_id: str, request: Request) -> dict[str, Any]:
    state = _state(request)
    try:
        return state.harness.replay(run_id)
    except ValueError as ex:
        raise HTTPException(status_code=404, detail=str(ex)) from ex


@router.post("/runs/{run_id}/cancel")
async def cancel(run_id: str, request: Request) -> dict[str, Any]:
    state = _state(request)
    return state.harness.to_view(await state.harness.cancel(run_id))


@router.post("/runs/{run_id}/clarify")
async def clarify(run_id: str, req: ClarifyRequest, request: Request) -> dict[str, Any]:
    state = _state(request)
    try:
        return state.harness.to_view(await state.harness.answer_clarification(run_id, req.answer))
    except RuntimeError as ex:
        raise HTTPException(status_code=409, detail=str(ex)) from ex


@router.post("/runs/{run_id}/intervene")
async def intervene(run_id: str, req: InterveneRequest, request: Request) -> dict[str, Any]:
    state = _state(request)
    try:
        return state.harness.to_view(
            await state.harness.intervene(run_id, req.type, req.text, req.expectedGoalVersion)
        )
    except RuntimeError as ex:
        raise HTTPException(status_code=409, detail=str(ex)) from ex
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex


@router.post("/runs/{run_id}/answer")
async def answer(run_id: str, req: AnswerRequest, request: Request) -> dict[str, Any]:
    state = _state(request)
    try:
        return state.harness.to_view(
            await state.harness.answer_pending(
                run_id, req.pendingId, req.goalVersion, req.decision, req.answer
            )
        )
    except RuntimeError as ex:
        raise HTTPException(status_code=409, detail=str(ex)) from ex


@router.get("/capabilities")
async def capabilities(request: Request) -> list[dict[str, Any]]:
    return list_capabilities(_state(request).registry)


@router.get("/device/state")
async def device_state(request: Request) -> dict[str, Any]:
    state = _state(request)
    snap = await state.simulator.read_state(None)
    return {
        "device_id": snap.device_id,
        "environment_id": snap.environment_id,
        "observed_at": snap.observed_at,
        "domain_revisions": snap.domain_revisions,
        "state": snap.state,
        "simulation": True,
        "note": "本地设备模拟器状态（联调/回归）",
    }


@router.post("/experiment/reset")
async def reset(request: Request) -> dict[str, Any]:
    return await _state(request).harness.reset_experiment()


@router.post("/experiment/force-new-environment")
async def force_env(request: Request) -> dict[str, Any]:
    await _state(request).simulator.force_new_environment()
    return await device_state(request)


@router.post("/experiment/fault")
async def fault(req: FaultRequest, request: Request) -> dict[str, Any]:
    state = _state(request)
    await state.simulator.inject_fault(FaultType(req.type), req.capabilityId, req.times or 1)
    return {"ok": True, "type": req.type, "capability_id": req.capabilityId, "times": req.times}


@router.post("/experiment/external-change")
async def external(req: ExternalChangeRequest, request: Request) -> dict[str, Any]:
    await _state(request).simulator.external_change(req.field, req.value)
    return await device_state(request)


@router.post("/evals/run")
async def run_eval(request: Request, mode: str = Query("agent")) -> dict[str, Any]:
    state = _state(request)
    if state.eval_runner is None:
        raise HTTPException(status_code=503, detail="eval runner unavailable")
    return await state.eval_runner.run(mode)


@router.get("/evals/last")
async def last_eval(request: Request) -> dict[str, Any]:
    state = _state(request)
    last = state.eval_runner.last_report if state.eval_runner else None
    if last is None:
        return {"available": False, "note": "尚未评测"}
    return last


@router.post("/experiment/require-confirmation")
async def require_confirmation(body: dict[str, Any], request: Request) -> dict[str, Any]:
    enabled = body.get("enabled") is True or str(body.get("enabled")).lower() == "true"
    set_require_confirmation(_state(request), enabled)
    return {"ok": True, "require_confirmation": _state(request).settings.require_confirmation}


@router.get("/meta")
async def meta(request: Request) -> dict[str, Any]:
    state = _state(request)
    return {
        "product": "Terminal Agent Runtime",
        "product_zh": "智能终端 Agent Runtime",
        "phase": "v1",
        "runtime": "python",
        "defaults_rule_id": "demo-defaults-v1",
        "local_simulator": True,
        "model_mode": state.model.mode(),
        "model_id": state.model_router.active_model_id,
        "model_placement": state.model_router.placement,
        "model_base_url": state.settings.model_base_url,
        "model_api_configured": bool(state.settings.model_api_key),
        "require_confirmation": state.settings.require_confirmation,
        "persistence": state.settings.persistence,
        "memory_enabled": True,
        "sse_enabled": True,
        "multi_agent": True,
        "agent_roles": ["MAIN", "PLANNER", "REVIEWER"],
        "disclaimer": (
            "智能终端 Agent Runtime；本地默认设备模拟器联调，模型为阶跃 Step（OpenAI-compatible），"
            "端云共用 ModelPort。复杂任务走主 Agent / 规划 / 审核三角色，写设备仍只经 Runtime。"
        ),
    }


@router.get("/memory")
async def list_memory(request: Request, sessionId: str = Query("web")) -> dict[str, Any]:
    state = _state(request)
    return {
        "session_id": sessionId,
        "memories": [m.to_map() for m in state.memory.list(sessionId)],
        "note": "长期记忆只影响默认值建议，不越过 Policy",
    }


@router.post("/memory")
async def write_memory(req: MemoryWriteRequest, request: Request) -> dict[str, Any]:
    state = _state(request)
    if req.utterance is not None and str(req.utterance).strip():
        return state.memory.try_write_from_utterance(
            req.utterance, req.sessionId or "web", req.sourceRunId
        )
    entry = MemoryEntry(
        session_id=req.sessionId or "web",
        category=req.category or "preference",
        key=req.key or "",
        value=req.value or "",
        domain=req.domain or "general",
        source_run_id=req.sourceRunId,
        confidence=0.9 if req.confidence is None else req.confidence,
        note="api_manual",
    )
    return state.memory.write_manual(entry)


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str, request: Request) -> dict[str, Any]:
    ok = _state(request).memory.delete(memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"ok": True, "id": memory_id}


@router.post("/model/placement")
async def set_placement(body: dict[str, Any], request: Request) -> dict[str, Any]:
    placement = str(body.get("placement", "cloud"))
    if placement.lower() not in {"cloud", "edge"}:
        raise HTTPException(status_code=400, detail="placement must be cloud|edge")
    state = _state(request)
    set_model_placement(state, placement)
    return {
        "ok": True,
        "placement": state.model_router.placement,
        "model_id": state.model_router.active_model_id,
        "note": "端侧为演进占位，非车规 NPU 部署",
    }
