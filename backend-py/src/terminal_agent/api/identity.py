"""Request identity: tenant / actor / trace. Missing tenant defaults to local."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from terminal_agent.contracts import new_id
from terminal_agent.orchestration.platform import sanitize_tenant_id


@dataclass(frozen=True)
class RequestIdentity:
    tenant_id: str
    actor: str
    trace_id: str


def identity_from(request: Request, default_tenant: str = "local") -> RequestIdentity:
    tenant = sanitize_tenant_id(request.headers.get("x-tenant-id"), default_tenant)
    actor = (request.headers.get("x-actor") or "anonymous").strip()[:64] or "anonymous"
    trace = (request.headers.get("x-trace-id") or "").strip() or new_id("tr")
    return RequestIdentity(tenant_id=tenant, actor=actor, trace_id=trace)
