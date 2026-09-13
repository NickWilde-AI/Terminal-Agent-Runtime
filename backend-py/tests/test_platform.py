"""Phase-1 platform: tenant isolation, auth, quota, circuit, audit, governance rules."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from terminal_agent.api.deps import build_app_state
from terminal_agent.api.sse import SseHub
from terminal_agent.capability.core import CapabilityRegistry
from terminal_agent.config import Settings
from terminal_agent.contracts import PolicyDecision, RunLifecycle, RunRecord
from terminal_agent.main import create_app
from terminal_agent.observability.audit import AuditLogger
from terminal_agent.orchestration.circuit import DomainCircuitBreaker
from terminal_agent.orchestration.quota import QuotaGovernor
from terminal_agent.policy.engine import PolicyEngine
from terminal_agent.policy.rules import GovernanceRules


def test_quota_concurrent_and_rate() -> None:
    quota = QuotaGovernor(max_concurrent_runs=1, max_runs_per_minute=0)
    assert quota.check("acme", 0) is None
    assert quota.check("acme", 1) == "TENANT_QUOTA_CONCURRENT"
    limited = QuotaGovernor(max_concurrent_runs=8, max_runs_per_minute=1)
    limited.note_created("acme")
    assert limited.check("acme", 0) == "TENANT_QUOTA_RATE"
    assert limited.check("other", 0) is None


def test_circuit_opens_on_threshold() -> None:
    breaker = DomainCircuitBreaker(2)
    assert breaker.allow("climate.set_temperature") is True
    assert breaker.record_failure("climate.set_power") is False
    assert breaker.record_failure("climate.set_temperature") is True
    assert breaker.allow("climate.set_fan") is False
    breaker.record_success("climate.set_temperature")
    assert breaker.allow("climate.set_fan") is True


def test_audit_redacts_secrets(tmp_path) -> None:
    logger = AuditLogger(str(tmp_path))
    logger.emit("run_created", detail={"api_key": "sk-live", "ok": True})
    rows = logger.tail(1)
    assert rows[0]["detail"]["api_key"] == "***"
    assert rows[0]["detail"]["ok"] is True


def test_governance_deny_writes_and_prod_forbidden() -> None:
    registry = CapabilityRegistry()
    paused = PolicyEngine(registry, rules=GovernanceRules(deny_writes=True))
    run = RunRecord(run_id="r", request_id="q", device_id="d", environment_id="e")
    denied = paused.decide(run, "climate.set_temperature", {"value": 23})
    assert denied.decision == PolicyDecision.DENY
    assert denied.code == "WRITES_PAUSED"

    prod = PolicyEngine(registry, rules=GovernanceRules(execution_environment="prod"))
    ok = prod.decide(run, "climate.set_temperature", {"value": 23})
    assert ok.decision == PolicyDecision.ALLOW
    risky = PolicyEngine(
        registry, rules=GovernanceRules(high_risk_capabilities=frozenset({"climate.set_temperature"}))
    )
    confirm = risky.decide(run, "climate.set_temperature", {"value": 23})
    assert confirm.decision == PolicyDecision.REQUIRE_CONFIRMATION


async def _client(tmp_path, **settings_kw):
    settings = Settings(
        model_mode="fake",
        persistence="memory",
        sqlite_path=str(tmp_path / "db.sqlite"),
        event_log_dir=str(tmp_path / "events"),
        audit_log_dir=str(tmp_path / "audit"),
        **settings_kw,
    )
    state = build_app_state(settings)
    state.memory_store.init()
    state.simulator.start_clock()
    hub = SseHub(state.store, state.simulator, state.harness)
    hub.wire()
    state.sse_hub = hub
    app = create_app(state)
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    return client, state, hub


@pytest.mark.asyncio
async def test_health_metrics_and_tenant_isolation(tmp_path) -> None:
    client, state, hub = await _client(tmp_path)
    try:
        health = await client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        created = await client.post(
            "/api/v1/runs",
            json={"text": "把空调设为 23 度", "sessionId": "web"},
            headers={"X-Tenant-Id": "alpha"},
        )
        assert created.status_code == 200, created.text
        run_id = created.json()["run_id"]
        await state.harness.await_idle(8_000)
        view = (await client.get(f"/api/v1/runs/{run_id}", headers={"X-Tenant-Id": "alpha"})).json()
        assert view["tenant_id"] == "alpha"
        assert view["lifecycle"] == "COMPLETED"
        hidden = await client.get(f"/api/v1/runs/{run_id}", headers={"X-Tenant-Id": "beta"})
        assert hidden.status_code == 404
        listed = await client.get("/api/v1/runs", headers={"X-Tenant-Id": "beta"})
        assert listed.json()["runs"] == []
        metrics = await client.get("/api/v1/metrics", headers={"X-Tenant-Id": "alpha"})
        assert metrics.status_code == 200
        assert metrics.json()["metrics"]["runs_created"] >= 1
        mem = await client.post(
            "/api/v1/memory",
            json={"utterance": "记住以后温度23度", "sessionId": "web", "sourceRunId": run_id},
            headers={"X-Tenant-Id": "alpha"},
        )
        assert mem.json()["accepted"] is True
        other = await client.get("/api/v1/memory?sessionId=web", headers={"X-Tenant-Id": "beta"})
        assert other.json()["memories"] == []
    finally:
        state.simulator.stop_clock()
        await hub.shutdown()
        await client.aclose()


@pytest.mark.asyncio
async def test_http_api_key_required(tmp_path) -> None:
    client, state, hub = await _client(tmp_path, http_api_key="secret-token")
    try:
        assert (await client.get("/api/v1/health")).status_code == 200
        assert (await client.get("/api/v1/meta")).status_code == 200
        denied = await client.get("/api/v1/runs")
        assert denied.status_code == 401
        allowed = await client.get("/api/v1/runs", headers={"X-Api-Key": "secret-token"})
        assert allowed.status_code == 200
    finally:
        state.simulator.stop_clock()
        await hub.shutdown()
        await client.aclose()


@pytest.mark.asyncio
async def test_quota_rejects_second_active_run(tmp_path) -> None:
    client, state, hub = await _client(tmp_path, max_concurrent_runs=1)
    try:
        first = await client.post("/api/v1/runs", json={"text": "把空调设为 23 度"})
        assert first.status_code == 200
        # Force a non-terminal occupant so quota, not the single-device lock, is the limiter.
        occupant = state.store.find(first.json()["run_id"])
        assert occupant is not None
        occupant.lifecycle = RunLifecycle.RUNNING
        second = await client.post("/api/v1/runs", json={"text": "把空调设为 24 度"})
        assert second.status_code == 429
        assert "TENANT_QUOTA" in second.json()["detail"]
    finally:
        state.simulator.stop_clock()
        await hub.shutdown()
        await client.aclose()
