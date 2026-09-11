#!/usr/bin/env bash
set -euo pipefail
# Hot-dev helper for the Python Runtime (default). Java: ./start.sh --local --java
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
export DEVICE_AGENT_WEB_DIST="${DEVICE_AGENT_WEB_DIST:-$ROOT/web/dist}"
cd "$ROOT/backend-py"
if command -v uv >/dev/null 2>&1; then
  exec uv run terminal-agent
fi
if [[ -x .venv/bin/terminal-agent ]]; then
  exec .venv/bin/terminal-agent
fi
exec .venv/bin/python -m uvicorn terminal_agent.main:app --host 0.0.0.0 --port 8080
