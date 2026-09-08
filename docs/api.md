# HTTP API

基础路径：`/api/v1`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/meta` | 实例元信息与模型配置 |
| GET | `/capabilities` | 工具注册表 |
| GET | `/device/state` | 当前设备状态 |
| POST | `/runs` | 创建任务（可异步执行） |
| GET | `/runs` | 任务列表 |
| GET | `/runs/{id}` | 任务详情 |
| GET | `/runs/{id}/events` | 事件流（`afterSeq` 增量，JSON） |
| GET | `/runs/{id}/events/stream` | 事件 SSE（`event`/`run`/`device`/`ping`） |
| GET | `/device/state/stream` | 设备状态 SSE |
| GET | `/runs/{id}/replay` | 只读回放 |
| POST | `/runs/{id}/cancel` | 取消 |
| POST | `/runs/{id}/clarify` | 澄清回答 |
| POST | `/runs/{id}/intervene` | 运行中改目标 |
| POST | `/runs/{id}/answer` | 确认批准 / 拒绝 |
| GET/POST/DELETE | `/memory` | 受控长期记忆 |
| POST | `/model/placement` | `cloud` / `edge` |
| POST | `/experiment/reset` | 先取消同设备活动任务，再重置模拟器 |
| POST | `/experiment/fault` | 故障注入 |
| POST | `/experiment/external-change` | 外部状态扰动 |
| POST | `/evals/run` | 跑评测 |
| GET | `/evals/last` | 最近评测报告 |

更多示例见 [`examples/`](../examples/)。
