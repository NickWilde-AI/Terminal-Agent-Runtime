# Terminal Agent Runtime — Python port

Python 3.12 rebuild of the Java Agent Runtime under `backend/`.

## Quick start

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

## Run API

```bash
export DEVICE_AGENT_MODEL_MODE=fake
# optional: DEVICE_AGENT_MODEL_API_KEY=... for openai_compatible
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

## Privacy

Do not commit `.env`, API keys, or anything under repo-root `private/`.
Use `.env.example` as the template.
