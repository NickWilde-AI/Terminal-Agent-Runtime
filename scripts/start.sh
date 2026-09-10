#!/usr/bin/env bash
set -euo pipefail

# Terminal Agent Runtime — one-click start
#   ./start.sh              # Docker Compose（默认）
#   ./start.sh --docker     # 同默认，显式 Docker
#   ./start.sh --local      # 本地进程（构建工作台 + Runtime，单端口 :8080）
#   ./start.sh --status
#   ./start.sh --stop
#   FORCE_REBUILD=1 ./start.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f deploy/compose/docker-compose.yml)
RUN_DIR="$ROOT/.run"
PID_FILE="$RUN_DIR/local.pid"
LOG_FILE="$RUN_DIR/local.log"

MODE="docker"
ACTION="start"
for arg in "$@"; do
  case "$arg" in
    --docker) MODE="docker" ;;
    --local) MODE="local" ;;
    --status) ACTION="status" ;;
    --stop) ACTION="stop" ;;
    -h|--help)
      sed -n '3,10p' "$0"
      exit 0
      ;;
    *)
      echo "未知参数: $arg（使用 --help 查看用法）" >&2
      exit 2
      ;;
  esac
done

api_ok() {
  curl -sf "http://127.0.0.1:8080/api/v1/meta" >/dev/null 2>&1
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
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  if ! grep -qE '^DEVICE_AGENT_MODEL_API_KEY=.+' .env \
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
}

stop_all() {
  stop_local
  if docker_available; then
    "${COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true
  fi
}

print_ready() {
  local how="$1"
  echo
  echo "已启动（${how}）→ http://localhost:8080"
  echo "状态 → ./start.sh --status"
  echo "停止 → ./start.sh --stop"
}

build_artifacts() {
  local need=0
  local jar
  jar="$(ls backend/target/terminal-agent-runtime-*.jar 2>/dev/null | head -1 || true)"
  if [[ "${FORCE_REBUILD:-0}" == "1" ]]; then
    need=1
  elif [[ -z "$jar" || ! -f web/dist/index.html ]]; then
    need=1
  fi
  if [[ "$need" == "1" ]]; then
    echo "==> 构建 Runtime"
    (cd backend && mvn -q -DskipTests package)
    echo "==> 构建工作台"
    (cd web && { [[ -d node_modules ]] || npm ci --silent; } && npm run build)
  else
    echo "==> 复用已有构建产物"
  fi
}

start_local() {
  echo "==> 本地一键模式（单进程 :8080 = 工作台 + API）"
  stop_all
  free_port 8080
  build_artifacts
  mkdir -p "$RUN_DIR" data reports
  local jar
  jar="$(ls backend/target/terminal-agent-runtime-*.jar | head -1)"
  export DEVICE_AGENT_WEB_DIST="$ROOT/web/dist"
  nohup java -jar "$jar" >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
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
  echo "==> Docker 一键模式"
  if ! ensure_docker; then
    echo "Docker 不可用，自动切换到本地一键模式"
    start_local
    return
  fi
  stop_local
  if api_ok && [[ "${FORCE_REBUILD:-0}" != "1" ]]; then
    echo "已在运行 → http://localhost:8080（强制重建: FORCE_REBUILD=1 ./start.sh）"
    exit 0
  fi
  if [[ "${FORCE_REBUILD:-0}" == "1" ]]; then
    "${COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true
  fi
  free_port 8080
  build_artifacts
  pull_image eclipse-temurin:21-jre
  pull_image nginx:1.27-alpine
  echo "==> docker compose up"
  "${COMPOSE[@]}" up --build -d
  for _ in $(seq 1 60); do
    if api_ok; then
      print_ready "Docker"
      exit 0
    fi
    sleep 2
  done
  echo "启动超时，请查看: docker compose -f deploy/compose/docker-compose.yml logs --tail=100" >&2
  exit 1
}

if [[ "$ACTION" == "status" ]]; then
  if api_ok; then
    echo "服务可用 → http://localhost:8080"
  else
    echo "服务不可用"
  fi
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "模式: 本地 (pid $(cat "$PID_FILE"))"
  elif docker_available; then
    "${COMPOSE[@]}" ps 2>/dev/null || true
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
