"""Single capability dispatch point with idempotency and reconciliation."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from terminal_agent.capability.core import CapabilityRegistry, effects_match, expected_effects
from terminal_agent.contracts import (
    Attribution,
    ExecutionStatus,
    PendingInteraction,
    PolicyDecision,
    RunLifecycle,
    RunPhase,
    RunRecord,
    StateSnapshot,
    ToolAction,
    VerificationStatus,
    new_id,
    now,
)
from terminal_agent.device.port import DeviceException, DevicePort
from terminal_agent.persistence.store import InMemoryRunStore
from terminal_agent.policy.engine import PolicyEngine


class CapabilityExecutor:
    def __init__(
        self,
        device: DevicePort,
        registry: CapabilityRegistry,
        policy: PolicyEngine,
        store: InMemoryRunStore,
        fresh_window_ms: int = 2000,
    ) -> None:
        self.device, self.registry, self.policy, self.store = device, registry, policy, store
        self.fresh_window_ms = fresh_window_ms

    def _fresh(self, run: RunRecord, snapshot: StateSnapshot) -> bool:
        return bool(
            snapshot.environment_id == run.environment_id
            and snapshot.observed_at
            and snapshot.observed_at > now() - timedelta(milliseconds=self.fresh_window_ms)
        )

    async def read(self, run: RunRecord, domains: set[Any] | None = None) -> StateSnapshot:
        run.budget.count_tool()
        await self.store.append_event(run, "READ_ATTEMPT", {})
        snapshot = await self.device.read_state(domains)
        await self.store.append_event(
            run,
            "OBSERVE",
            {"state": snapshot.state, "revisions": snapshot.domain_revisions, "observed_at": snapshot.observed_at},
        )
        if not self._fresh(run, snapshot):
            raise DeviceException("STALE_STATE", "缺少当前环境的新鲜快照")
        return snapshot

    async def execute_write(
        self,
        run: RunRecord,
        capability_id: str,
        params: dict[str, Any],
        version: int | None = None,
        planned: StateSnapshot | None = None,
    ) -> ToolAction:
        version = run.task.goal_version if version is None else version
        action = ToolAction(
            action_id=new_id("act"),
            idempotency_key="",
            run_id=run.run_id,
            goal_version=version,
            environment_id=run.environment_id,
            capability_id=capability_id,
            params=dict(params or {}),
            execution_status=ExecutionStatus.PROPOSED,
        )
        action.idempotency_key = action.action_id
        before = planned or await self.read(run, set())
        run.actions.append(action)
        await self.store.append_event(
            run,
            "ACTION_PROPOSED",
            {"action_id": action.action_id, "capability_id": capability_id, "params": params, "goal_version": version},
        )
        if (
            run.is_terminal()
            or run.cancel_accepted
            or version != run.task.goal_version
            or run.environment_id != self.device.environment_id
        ):
            return await self._reject(run, action, ExecutionStatus.CANCELLED_BEFORE_DISPATCH, "过期目标、环境或已取消")
        if run.in_flight_action_id or run.unresolved_unknown:
            return await self._reject(run, action, ExecutionStatus.REJECTED, "另有在途或未知动作")
        decision = self.policy.decide(run, capability_id, params)
        await self.store.append_event(
            run,
            "POLICY",
            {"action_id": action.action_id, "decision": decision.decision.value, "message": decision.message},
        )
        if decision.decision == PolicyDecision.DENY:
            return await self._reject(
                run, action, ExecutionStatus.REJECTED, decision.message or decision.code or "DENIED"
            )
        if not self._fresh(run, before):
            return await self._reject(run, action, ExecutionStatus.REJECTED, "状态快照过期")
        if decision.decision == PolicyDecision.REQUIRE_CONFIRMATION:
            run.pending = PendingInteraction(
                type="CONFIRMATION",
                goal_version=version,
                capability_id=capability_id,
                params=dict(params),
                expires_at=run.budget.deadline or now(),
                question=f"确认执行 {capability_id} {params}",
            )
            run.lifecycle, run.phase = RunLifecycle.WAITING_CONFIRMATION, RunPhase.WAIT
            await self.store.append_event(run, "WAIT_CONFIRMATION", run.pending.to_map())
            return action
        action.execution_status = ExecutionStatus.AUTHORIZED
        await self.store.append_event(run, "AUTHORIZED", {"action_id": action.action_id})
        action.expected_revisions, action.deadline = dict(before.domain_revisions), run.budget.deadline
        run.budget.count_write()
        run.budget.count_tool()
        await self.store.append_event(
            run, "ACTION_INTENT", {"action_id": action.action_id, "idempotency_key": action.idempotency_key}
        )
        action.execution_status, action.dispatched_at = ExecutionStatus.DISPATCHED, now()
        run.in_flight_action_id = action.action_id
        await self.store.append_event(
            run,
            "DISPATCH",
            {"action_id": action.action_id, "capability_id": capability_id, "params": params, "goal_version": version},
        )
        try:
            record = await self.device.apply_write(
                action.action_id,
                action.idempotency_key,
                capability_id,
                params,
                action.environment_id,
                action.deadline,
                action.expected_revisions,
                run.run_id,
                version,
            )
            action.execution_status = ExecutionStatus.ACKNOWLEDGED
            await self.store.append_event(run, "ACKNOWLEDGED", {"action_id": action.action_id})
            await self._record(run, action, record)
        except DeviceException as exc:
            action.execution_status, action.message = ExecutionStatus.UNKNOWN, exc.code
            run.unresolved_unknown = True
            await self.store.append_event(
                run, "TOOL_RESULT", {"action_id": action.action_id, "execution_status": "UNKNOWN", "code": exc.code}
            )
        if action.execution_status == ExecutionStatus.UNKNOWN:
            for _ in range(4):
                if action.execution_status != ExecutionStatus.UNKNOWN:
                    break
                await asyncio.sleep(0.06)
                if hasattr(self.device, "tick"):
                    await self.device.tick()
                await self.reconcile_unknown(run, action)
        await self._verify(run, action)
        if action.execution_status != ExecutionStatus.UNKNOWN:
            run.in_flight_action_id = None
        run.unresolved_unknown = action.execution_status == ExecutionStatus.UNKNOWN
        await self.store.append_event(
            run, "ACTION_SETTLED", {"action_id": action.action_id, "execution_status": action.execution_status.value}
        )
        return action

    async def _reject(self, run: RunRecord, action: ToolAction, status: ExecutionStatus, reason: str) -> ToolAction:
        action.execution_status, action.message, action.finished_at = status, reason, now()
        await self.store.append_event(
            run, "ACTION_REJECTED", {"action_id": action.action_id, "execution_status": status.value, "message": reason}
        )
        return action

    async def _record(self, run: RunRecord, action: ToolAction, record: Any) -> None:
        action.execution_status = {
            "APPLIED": ExecutionStatus.APPLIED,
            "NOT_APPLIED": ExecutionStatus.NOT_APPLIED,
        }.get(record.status, ExecutionStatus.UNKNOWN)
        action.message, action.finished_at = record.message, record.finished_at
        action.evidence["device_revision"] = record.revision
        if record.status == "APPLIED" and record.action_id == action.action_id:
            action.attribution = Attribution.THIS_ACTION
        run.unresolved_unknown = action.execution_status == ExecutionStatus.UNKNOWN
        await self.store.append_event(
            run,
            "TOOL_RESULT",
            {
                "action_id": action.action_id,
                "execution_status": action.execution_status.value,
                "message": record.message,
            },
        )

    async def reconcile_unknown(self, run: RunRecord, action: ToolAction) -> None:
        if not run.is_terminal():
            run.budget.count_tool()
        await self.store.append_event(run, "RECONCILE_ATTEMPT", {"action_id": action.action_id})
        record = await self.device.query_action(action.action_id)
        if record is not None:
            await self._record(run, action, record)
        await self.store.append_event(
            run, "RECONCILE", {"action_id": action.action_id, "execution_status": action.execution_status.value}
        )

    async def _verify(self, run: RunRecord, action: ToolAction) -> None:
        await self.store.append_event(run, "VERIFY_ATTEMPT", {"action_id": action.action_id})
        try:
            if not run.is_terminal():
                run.budget.count_tool()
            snapshot = await self.device.read_state(None)
            matches = effects_match(action.capability_id, action.params, snapshot.state)
            action.verification_status = (
                VerificationStatus.STALE
                if not self._fresh(run, snapshot)
                else VerificationStatus.SATISFIED
                if matches
                else VerificationStatus.NOT_SATISFIED
            )
            own = all(
                snapshot.origins.get(field, {}).get("action_id") == action.action_id
                for field in expected_effects(action.capability_id, action.params)
            )
            if matches and not own:
                action.attribution = Attribution.EXTERNAL
            action.evidence.update(after_state=snapshot.state, origins=snapshot.origins, revision=snapshot.revision)
        except Exception:
            action.verification_status = VerificationStatus.UNAVAILABLE
        await self.store.append_event(
            run,
            "VERIFY",
            {
                "action_id": action.action_id,
                "verification_status": action.verification_status.value,
                "attribution": action.attribution.value,
            },
        )
