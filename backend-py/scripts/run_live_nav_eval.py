#!/usr/bin/env python3
"""Run a filtered live-model eval subset and write a sanitized public summary.

Usage (from repo root, with .env configured):

  cd backend-py
  uv run python scripts/run_live_nav_eval.py

Never prints API keys. Full raw report stays under backend-py/reports/ (gitignored).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_PY = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "docs" / "reports"


def _load_root_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def _sanitize(report: dict) -> dict:
    cases = []
    for item in report.get("cases") or []:
        cases.append(
            {
                "id": item.get("id"),
                "category": item.get("category"),
                "completable": item.get("completable"),
                "passed": item.get("passed"),
                "false_success": item.get("false_success"),
                "lifecycle": item.get("lifecycle"),
                "route": item.get("route"),
                "message": item.get("message"),
                "stop_reason": item.get("stop_reason"),
            }
        )
    return {
        "title": "Live model navigation subset (N01–N12)",
        "mode": report.get("mode"),
        "dataset_version": report.get("dataset_version"),
        "model_mode": report.get("model_mode"),
        "model_id": report.get("model_id"),
        "case_filter": report.get("case_filter"),
        "total": report.get("total"),
        "passed": report.get("passed"),
        "failed": report.get("failed"),
        "correct_handling_rate": report.get("correct_handling_rate"),
        "false_success": report.get("false_success"),
        "generated_at": report.get("generated_at"),
        "environment": {
            "device": "local DeviceSimulator",
            "runtime": "python",
            "note": "OpenAI-compatible cloud model + local simulator; not a company production score.",
        },
        "cases": cases,
        "boundaries": [
            "This is a public credibility sample, not the Fake 54 gate.",
            "Fake 54 / false_success=0 remains the deterministic CI gate.",
            "No API keys, prompts, or raw model payloads are included.",
        ],
    }


async def main() -> int:
    _load_root_env()
    os.chdir(BACKEND_PY)
    sys.path.insert(0, str(BACKEND_PY / "src"))

    from terminal_agent.api.deps import build_app_state
    from terminal_agent.config import Settings

    if not os.environ.get("DEVICE_AGENT_MODEL_API_KEY", "").strip():
        print("DEVICE_AGENT_MODEL_API_KEY missing; refuse to run live eval.", file=sys.stderr)
        return 2

    settings = Settings(
        model_mode=os.environ.get("DEVICE_AGENT_MODEL_MODE", "openai_compatible"),
        model_base_url=os.environ.get("DEVICE_AGENT_MODEL_BASE_URL", "https://api.stepfun.com/v1"),
        model_api_key=os.environ.get("DEVICE_AGENT_MODEL_API_KEY", ""),
        model_id=os.environ.get("DEVICE_AGENT_MODEL_ID", "step-3.5-flash"),
        persistence="memory",
        sqlite_path=str(BACKEND_PY / "data" / "live-eval.db"),
        event_log_dir=str(BACKEND_PY / "data" / "events-live-eval"),
        require_confirmation=False,
    )
    state = build_app_state(settings)
    state.simulator.start_clock()
    assert state.eval_runner is not None
    state.eval_runner.report_dir = BACKEND_PY / "reports"

    print(
        f"Running live nav eval: model_mode={settings.model_mode} model_id={settings.model_id} "
        f"api_configured={bool(settings.model_api_key)}",
        flush=True,
    )
    report = await state.eval_runner.run("agent", id_prefix="N")
    summary = _sanitize(report)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    out = PUBLIC_DIR / "live-nav-agent-summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "total": summary["total"],
                "passed": summary["passed"],
                "failed": summary["failed"],
                "false_success": summary["false_success"],
                "correct_handling_rate": summary["correct_handling_rate"],
                "public_summary": str(out),
                "raw_report": report.get("report_path"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
