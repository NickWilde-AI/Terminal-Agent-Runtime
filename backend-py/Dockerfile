FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data/events /app/reports

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /uvx /bin/

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Install project + deps into /.venv (no editable — container image).
RUN uv sync --frozen --no-dev --no-editable

ENV PATH="/app/.venv/bin:$PATH" \
    DEVICE_AGENT_EVENT_LOG_DIR=/app/data/events \
    DEVICE_AGENT_SQLITE_PATH=/app/data/harness.db \
    DEVICE_AGENT_PERSISTENCE=sqlite \
    PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=3s --retries=20 --start-period=25s \
  CMD curl -sf http://127.0.0.1:8080/api/v1/meta >/dev/null || exit 1

CMD ["uvicorn", "terminal_agent.main:app", "--host", "0.0.0.0", "--port", "8080"]
