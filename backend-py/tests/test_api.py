"""Minimal FastAPI contract smoke."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from terminal_agent.api.deps import build_app_state
from terminal_agent.api.sse import SseHub
from terminal_agent.config import Settings
from terminal_agent.main import create_app


@pytest.mark.asyncio
async def test_meta_and_fast_run() -> None:
    settings = Settings(
        model_mode="fake",
        persistence="memory",
        sqlite_path="./data/test-api.db",
        event_log_dir="./data/events-api-test",
    )
    state = build_app_state(settings)
    state.memory_store.init()
    state.simulator.start_clock()
    hub = SseHub(state.store, state.simulator, state.harness)
    hub.wire()
    state.sse_hub = hub
    app = create_app(state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        meta = await client.get("/api/v1/meta")
        assert meta.status_code == 200
        assert meta.json()["model_mode"] == "fake"
        created = await client.post("/api/v1/runs", json={"text": "把空调设为 23 度", "sessionId": "eval"})
        assert created.status_code == 200, created.text
        run_id = created.json()["run_id"]
        # Prefer direct harness wait — ASGI may not interleave background tasks reliably.
        await state.harness.await_idle(8_000)
        view = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if view["lifecycle"] in {"RECEIVED", "RUNNING"}:
            for _ in range(40):
                await asyncio.sleep(0.05)
                view = (await client.get(f"/api/v1/runs/{run_id}")).json()
                if view["lifecycle"] not in {"RECEIVED", "RUNNING", "WAITING_CLARIFICATION", "WAITING_CONFIRMATION"}:
                    break
        assert view["lifecycle"] == "COMPLETED", view
        assert view["route"] == "FAST"
        mem = await client.post(
            "/api/v1/memory",
            json={"utterance": "记住以后温度23度", "sessionId": "web", "sourceRunId": run_id},
        )
        assert mem.status_code == 200
        assert mem.json()["accepted"] is True
    state.simulator.stop_clock()
    await hub.shutdown()
