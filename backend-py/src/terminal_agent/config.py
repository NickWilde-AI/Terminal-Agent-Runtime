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

    # Nested via composition (also readable from flat DEVICE_AGENT_MODEL_*).
    model_mode: str = Field(default="openai_compatible", validation_alias="MODEL_MODE")
    model_base_url: str = Field(default="https://api.stepfun.com/v1", validation_alias="MODEL_BASE_URL")
    model_api_key: str = Field(default="", validation_alias="MODEL_API_KEY")
    model_id: str = Field(default="step-3.5-flash", validation_alias="MODEL_ID")
    model_edge_id: str = Field(default="step-edge-stub", validation_alias="MODEL_EDGE_ID")
    model_placement: str = Field(default="cloud", validation_alias="MODEL_PLACEMENT")
    model_timeout_ms: int = Field(default=60_000, validation_alias="MODEL_TIMEOUT_MS")

    absolute_deadline_seconds: int = 120
    max_model_calls: int = 12
    max_tool_calls: int = 24
    max_write_actions: int = 6
    max_replans: int = 2
    max_same_failure: int = 2

    def ensure_dirs(self) -> None:
        Path(self.event_log_dir).mkdir(parents=True, exist_ok=True)
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
