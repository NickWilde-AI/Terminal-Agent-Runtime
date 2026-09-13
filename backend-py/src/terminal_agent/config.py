"""Application settings — DEVICE_AGENT_* env parity with Java application.yml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BudgetSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEVICE_AGENT_BUDGET_")

    absolute_deadline_seconds: int = 120
    max_model_calls: int = 12
    max_tool_calls: int = 24
    max_write_actions: int = 6
    max_replans: int = 2
    max_same_failure: int = 2


class ModelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEVICE_AGENT_MODEL_")

    mode: str = Field(default="openai_compatible")  # fake | openai_compatible
    base_url: str = "https://api.stepfun.com/v1"
    api_key: str = ""
    model_id: str = "step-3.5-flash"
    edge_model_id: str = "step-edge-stub"
    placement: str = "cloud"  # cloud | edge
    timeout_ms: int = 60_000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="DEVICE_AGENT_",
    )

    defaults_rule_id: str = "demo-defaults-v1"
    fresh_window_ms: int = 2000
    web_dist: str = ""
    event_log_dir: str = "./data/events"
    require_confirmation: bool = False
    persistence: str = "sqlite"  # sqlite | memory
    sqlite_path: str = "./data/harness.db"
    host: str = "0.0.0.0"
    port: int = 8080

    # Flat DEVICE_AGENT_MODEL_* (env_prefix DEVICE_AGENT_ → DEVICE_AGENT_MODEL_MODE 等)
    model_mode: str = "openai_compatible"
    model_base_url: str = "https://api.stepfun.com/v1"
    model_api_key: str = ""
    model_id: str = "step-3.5-flash"
    model_edge_id: str = "step-edge-stub"
    model_placement: str = "cloud"
    model_timeout_ms: int = 60_000

    absolute_deadline_seconds: int = 120
    max_model_calls: int = 12
    max_tool_calls: int = 24
    max_write_actions: int = 6
    max_replans: int = 2
    max_same_failure: int = 2

    # Platform / governance (Phase-1 local production-ready layer)
    tenant_id: str = "local"
    http_api_key: str = ""
    execution_environment: str = "sim"
    deny_writes: bool = False
    max_concurrent_runs: int = 8
    max_runs_per_minute: int = 0
    circuit_breaker_failures: int = 0
    high_risk_capabilities: str = ""
    work_hours_start: int | None = None
    work_hours_end: int | None = None
    audit_log_dir: str = "./data/audit"

    def ensure_dirs(self) -> None:
        Path(self.event_log_dir).mkdir(parents=True, exist_ok=True)
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.audit_log_dir).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
