# 示例请求

```bash
BASE=http://127.0.0.1:8080

curl -s "$BASE/api/v1/meta"

curl -X POST "$BASE/api/v1/experiment/reset"

curl -X POST "$BASE/api/v1/runs" \
  -H 'Content-Type: application/json' \
  -d '{"text":"把空调设为 23 度","requestId":"demo-1","sessionId":"demo"}'

curl -X POST "$BASE/api/v1/runs" \
  -H 'Content-Type: application/json' \
  -d '{"text":"环境调舒服一点：温度合适、媒体小声，导航提示保留。","requestId":"demo-2","sessionId":"demo"}'

curl -X POST "$BASE/api/v1/memory" \
  -H 'Content-Type: application/json' \
  -d '{"utterance":"记住我喜欢温度24度","sessionId":"demo","sourceRunId":"manual-1"}'

curl -X POST "$BASE/api/v1/evals/run?mode=agent"
```
