"""Core runtime domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RouteType(StrEnum):
    CHAT = "CHAT"
    FAST = "FAST"
    AGENT = "AGENT"
    MULTI_AGENT = "MULTI_AGENT"
    CLARIFY = "CLARIFY"
    REJECT = "REJECT"

    def is_complex_agent(self) -> bool:
        return self in {self.AGENT, self.MULTI_AGENT}


class ReviewDecision(StrEnum):
    PASS = "PASS"
    REVISE = "REVISE"
    REJECT = "REJECT"


class ChangeSource(StrEnum):
    THIS_TASK = "THIS_TASK"
    EXTERNAL_OPERATOR = "EXTERNAL_OPERATOR"
    SIMULATOR_INTERNAL = "SIMULATOR_INTERNAL"
    UNKNOWN = "UNKNOWN"


class AgentRole(StrEnum):
    MAIN = "MAIN"
    PLANNER = "PLANNER"
    REVIEWER = "REVIEWER"


class DeviceDomain(StrEnum):
    CABIN = "CABIN"
    MEDIA = "MEDIA"
    NAVIGATION = "NAVIGATION"
    AUDIO = "AUDIO"
    LIFE = "LIFE"
    IOT = "IOT"


class Criterion(BaseModel):
    criterion_id: str
    template_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    required: bool = True
    source_ref: str
    baseline_observation: dict[str, Any] = Field(default_factory=dict)
    bound_goal_version: int
    bound_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DeviceTask(BaseModel):
    run_id: str
    goal_version: int = 1
    raw_text: str
    defaults_rule_id: str = "demo-defaults-v1"
    goals: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    criteria: list[Criterion] = Field(default_factory=list)
    binding_context: dict[str, Any] = Field(default_factory=dict)


class StateSnapshot(BaseModel):
    revision: int = 0
    origins: dict[str, dict[str, Any]] = Field(default_factory=dict)
    device_id: str | None = None
    environment_id: str | None = None
    domain_revisions: dict[str, int] = Field(default_factory=dict)
    observed_at: datetime | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    change_source: ChangeSource = ChangeSource.UNKNOWN
    action_id: str | None = None
