# Terminal Agent Runtime — Python（公开主实现）

Python 3.12 Agent Runtime。讲解、一键启动与回归默认以本目录为准；Java（`../backend/`）经 `./start.sh --java` 对照。

## Quick start（仓库根目录）

```bash
cp .env.example .env
DEVICE_AGENT_MODEL_MODE=fake ./start.sh --local   # 无需 JDK；工作台 + API → :8080
curl -s http://localhost:8080/api/v1/meta         # "runtime":"python"
```

## Tests

```bash
cd backend-py
uv sync --extra dev
source .venv/bin/activate
export DEVICE_AGENT_MODEL_MODE=fake
pytest tests/ -q
```

Or without activating:

```bash
DEVICE_AGENT_MODEL_MODE=fake uv run pytest tests/ -q
```

## Run API（仅后端，可选）

```bash
export DEVICE_AGENT_MODEL_MODE=fake
# optional: DEVICE_AGENT_MODEL_API_KEY=... for openai_compatible
# optional: DEVICE_AGENT_WEB_DIST=../web/dist  to serve the workbench
uv run terminal-agent
```

Default listen: `0.0.0.0:8080`, API prefix `/api/v1`.

## Layout

- `src/terminal_agent/runtime/` — harness, goal compiler, executor, verifier
- `src/terminal_agent/device/` — simulator DevicePort
- `src/terminal_agent/model/` — Fake / OpenAI-compatible adapters
- `src/terminal_agent/eval/` — 54-seed catalog + runner
- `src/terminal_agent/memory/` — write gate + retriever
- `src/terminal_agent/api/` — FastAPI routes + SSE
- `tests/` — pytest including FakeEvalGate (54/54)
- `Dockerfile` — used by default `deploy/compose/docker-compose.yml`

## Privacy

Do not commit `.env`, API keys, or anything under repo-root `private/`.
Use `.env.example` as the template.
