#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8080}"
echo "==> GET $BASE/api/v1/meta"
curl -sf "$BASE/api/v1/meta" | head -c 400
echo
echo "==> POST reset"
curl -sf -X POST "$BASE/api/v1/experiment/reset" >/dev/null
echo "==> POST run"
curl -sf -X POST "$BASE/api/v1/runs" \
  -H 'Content-Type: application/json' \
  -d '{"text":"把空调设为 23 度","requestId":"smoke-1","sessionId":"smoke"}' | head -c 500
echo
echo "smoke ok"
