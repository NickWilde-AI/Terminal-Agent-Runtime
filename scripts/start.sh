#!/usr/bin/env bash
set -euo pipefail

# Terminal Agent Runtime — one-click start
#   ./start.sh                 # Docker + Python（默认）
#   ./start.sh --python        # 显式 Python（同默认）
#   ./start.sh --java          # Java 历史对照
#   ./start.sh --docker        # 显式 Docker（默认）
#   ./start.sh --local         # 本地单进程 :8080（默认 Python，无需 JDK）
#   ./start.sh --local --java  # 本地 Java 对照（需要 JDK/Maven）
#   ./start.sh --status
#   ./start.sh --stop
#   FORCE_REBUILD=1 ./start.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
RUN_DIR="$ROOT/.run"
PID_FILE="$RUN_DIR/local.pid"
LOG_FILE="$RUN_DIR/local.log"
RUNTIME_FILE="$RUN_DIR/runtime"

MODE="docker"
ACTION="start"
RUNTIME="python"

for arg in "$@"; do
  case "$arg" in
    --docker) MODE="docker" ;;
    --local) MODE="local" ;;
    --python) RUNTIME="python" ;;
    --java) RUNTIME="java" ;;
    --status|status) ACTION="status" ;;
    --stop|stop) ACTION="stop" ;;
    -h|--help)
      sed -n '3,14p' "$0"
      exit 0
      ;;
    *)
      printf '未知参数: %s（使用 --help 查看用法）\n' "$arg" >&2
      exit 2
      ;;
  esac
done

compose_files() {
  if [[ "$RUNTIME" == "java" ]]; then
    echo "-f" "deploy/compose/docker-compose.java.yml"
  else
    echo "-f" "deploy/compose/docker-compose.yml"
  fi
}

COMPOSE=(docker compose)
# shellcheck disable=SC2207
COMPOSE+=($(compose_files))

api_ok() {
  curl -sf "http://127.0.0.1:8080/api/v1/meta" >/dev/null 2>&1
}

api_runtime() {
  curl -sf "http://127.0.0.1:8080/api/v1/meta" 2>/dev/null \
    | python3 -c 'import sys,json; print(json.load(sys.stdin).get("runtime","unknown"))' 2>/dev/null \
    || echo "unknown"
}

docker_available() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

ensure_docker() {
  if docker_available; then
    return 0
  fi
  echo "Docker 未运行，正在尝试启动 Docker Desktop..."
  open -a Docker 2>/dev/null || open -a "Docker Desktop" 2>/dev/null || true
  for _ in $(seq 1 60); do
    if docker_available; then
      return 0
    fi
    sleep 2
  done
  return 1
}

load_env() {
  if [[ ! -f .env ]]; then
    echo "缺少 .env。请先: cp .env.example .env 并填写 DEVICE_AGENT_MODEL_API_KEY" >&2
    exit 1
  fi
  # Preserve explicit shell overrides (e.g. DEVICE_AGENT_MODEL_MODE=fake ./start.sh)
  local preserve_mode="${DEVICE_AGENT_MODEL_MODE-}"
  local preserve_key="${DEVICE_AGENT_MODEL_API_KEY-}"
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  if [[ -n "${preserve_mode}" ]]; then
    export DEVICE_AGENT_MODEL_MODE="$preserve_mode"
  fi
  if [[ -n "${preserve_key}" ]]; then
    export DEVICE_AGENT_MODEL_API_KEY="$preserve_key"
  fi
  if ! grep -qE '^DEVICE_AGENT_MODEL_API_KEY=.+' .env \
      && [[ -z "${DEVICE_AGENT_MODEL_API_KEY:-}" ]] \
      && [[ "${DEVICE_AGENT_MODEL_MODE:-}" != "fake" ]]; then
    echo "警告: .env 中 DEVICE_AGENT_MODEL_API_KEY 为空，模型调用会失败（可用 DEVICE_AGENT_MODEL_MODE=fake）"
  fi
}

free_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
  fi
}

stop_local() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi
  rm -f "$RUNTIME_FILE"
}

stop_all() {
  stop_local
  if docker_available; then
    docker compose -f deploy/compose/docker-compose.yml down --remove-orphans >/dev/null 2>&1 || true
    docker compose -f deploy/compose/docker-compose.java.yml down --remove-orphans >/dev/null 2>&1 || true
  fi
}

print_ready() {
  local how="$1"
  local rt
  rt="$(api_runtime)"
  echo
  echo "已启动（${how} / runtime=${rt}）→ http://localhost:8080"
  echo "状态 → ./start.sh --status"
  echo "停止 → ./start.sh --stop"
  if [[ "$RUNTIME" == "python" ]]; then
    echo "对照 → ./start.sh --java   # Java 历史实现"
  else
    echo "默认 → ./start.sh --python # Python 主实现"
  fi
}

need_web_build() {
  [[ "${FORCE_REBUILD:-0}" == "1" || ! -f web/dist/index.html ]]
}

build_web() {
  if need_web_build; then
    echo "==> 构建工作台"
    (cd web && { [[ -d node_modules ]] || npm ci --silent; } && npm run build)
  else
    echo "==> 复用已有 web/dist"
  fi
}

build_java_jar() {
  local jar
  jar="$(ls backend/target/terminal-agent-runtime-*.jar 2>/dev/null | head -1 || true)"
  if [[ "${FORCE_REBUILD:-0}" == "1" || -z "$jar" ]]; then
    echo "==> 构建 Java Runtime（legacy）"
    if ! command -v mvn >/dev/null 2>&1; then
      echo "缺少 Maven；--java 本地/镜像构建需要 JDK 21 + Maven 3.9+" >&2
      exit 1
    fi
    (cd backend && mvn -q -DskipTests package)
  else
    echo "==> 复用已有 Java jar"
  fi
}

ensure_python_env() {
  if [[ -x "$ROOT/backend-py/.venv/bin/python" && "${FORCE_REBUILD:-0}" != "1" ]]; then
    # Ensure console script exists.
    if [[ -x "$ROOT/backend-py/.venv/bin/terminal-agent" ]] \
      || "$ROOT/backend-py/.venv/bin/python" -c "import terminal_agent" 2>/dev/null; then
      return 0
    fi
  fi
  echo "==> 准备 Python Runtime 依赖（无需 JDK）"
  if command -v uv >/dev/null 2>&1; then
    (cd "$ROOT/backend-py" && uv sync --extra dev)
  else
    if [[ ! -x "$ROOT/backend-py/.venv/bin/python" ]]; then
      python3 -m venv "$ROOT/backend-py/.venv"
    fi
    "$ROOT/backend-py/.venv/bin/pip" install -q -U pip
    "$ROOT/backend-py/.venv/bin/pip" install -q -e "$ROOT/backend-py[dev]"
  fi
}

run_python_local() {
  mkdir -p "$RUN_DIR" data reports
  export DEVICE_AGENT_WEB_DIST="$ROOT/web/dist"
  export PYTHONUNBUFFERED=1
  local cmd
  if command -v uv >/dev/null 2>&1 && [[ -f "$ROOT/backend-py/uv.lock" ]]; then
    cmd=(uv run terminal-agent)
  elif [[ -x "$ROOT/backend-py/.venv/bin/terminal-agent" ]]; then
    cmd=(.venv/bin/terminal-agent)
  else
    cmd=(.venv/bin/python -m uvicorn terminal_agent.main:app --host 0.0.0.0 --port 8080)
  fi
  (
    cd "$ROOT/backend-py"
    exec nohup "${cmd[@]}"
  ) >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "python" >"$RUNTIME_FILE"
}

run_java_local() {
  mkdir -p "$RUN_DIR" data reports
  local jar
  jar="$(ls backend/target/terminal-agent-runtime-*.jar | head -1)"
  export DEVICE_AGENT_WEB_DIST="$ROOT/web/dist"
  nohup java -jar "$jar" >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "java" >"$RUNTIME_FILE"
}

start_local() {
  echo "==> 本地一键模式（单进程 :8080 = 工作台 + API，runtime=${RUNTIME}）"
  stop_all
  free_port 8080
  build_web
  if [[ "$RUNTIME" == "java" ]]; then
    build_java_jar
    run_java_local
  else
    ensure_python_env
    run_python_local
  fi
  for _ in $(seq 1 60); do
    if api_ok; then
      print_ready "本地"
      exit 0
    fi
    sleep 1
  done
  echo "本地启动超时，日志: $LOG_FILE" >&2
  tail -n 80 "$LOG_FILE" >&2 || true
  exit 1
}

pull_image() {
  local image="$1"
  if docker image inspect "$image" >/dev/null 2>&1; then
    return 0
  fi
  if ! docker pull "$image"; then
    echo "Docker Hub 拉取失败，尝试 DaoCloud 镜像: $image"
    local mirror="docker.m.daocloud.io/library/${image}"
    docker pull "$mirror"
    docker tag "$mirror" "$image"
  fi
}

start_docker() {
  echo "==> Docker 一键模式（runtime=${RUNTIME}）"
  if ! ensure_docker; then
    echo "Docker 不可用，自动切换到本地一键模式"
    start_local
    return
  fi
  stop_local
  if api_ok && [[ "${FORCE_REBUILD:-0}" != "1" ]]; then
    echo "已在运行 → http://localhost:8080（runtime=$(api_runtime)；强制重建: FORCE_REBUILD=1 ./start.sh）"
    exit 0
  fi
  if [[ "${FORCE_REBUILD:-0}" == "1" ]]; then
    stop_all
  fi
  free_port 8080
  build_web
  if [[ "$RUNTIME" == "java" ]]; then
    build_java_jar
    pull_image eclipse-temurin:21-jre
  else
    pull_image python:3.12-slim
  fi
  pull_image nginx:1.27-alpine
  echo "==> docker compose up (${RUNTIME})"
  "${COMPOSE[@]}" up --build -d
  for _ in $(seq 1 90); do
    if api_ok; then
      print_ready "Docker"
      exit 0
    fi
    sleep 2
  done
  echo "启动超时，请查看: docker compose $(compose_files) logs --tail=100" >&2
  exit 1
}

if [[ "$ACTION" == "status" ]]; then
  if api_ok; then
    echo "服务可用 → http://localhost:8080（runtime=$(api_runtime)）"
  else
    echo "服务不可用"
  fi
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "模式: 本地 (pid $(cat "$PID_FILE"), runtime=$(cat "$RUNTIME_FILE" 2>/dev/null || echo unknown))"
  elif docker_available; then
    docker compose -f deploy/compose/docker-compose.yml ps 2>/dev/null || true
    docker compose -f deploy/compose/docker-compose.java.yml ps 2>/dev/null || true
  fi
  exit 0
fi

if [[ "$ACTION" == "stop" ]]; then
  stop_all
  free_port 8080
  echo "已停止"
  exit 0
fi

load_env

case "$MODE" in
  local) start_local ;;
  docker|*) start_docker ;;
esac
