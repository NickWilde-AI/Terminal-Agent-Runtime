# Live model evaluation sample（公开可信度样本）

> **定位：** 用真实 OpenAI 兼容云端模型 + 本地 `DeviceSimulator`，对出行导航子集 **N01–N12** 做一次可复现抽检。  
> **不是：** 公司量产分数、行业 Benchmark、或替代 Fake 门禁。

## 与 Fake 门禁的关系

| 项 | Fake 54 门禁 | 本样本 |
| --- | --- | --- |
| 目的 | CI / 执行语义回归 | 证明「真模型也能进 Runtime」 |
| 模型 | `fake`（确定性） | `openai_compatible`（本机记录：`step-3.5-flash`） |
| 规模 | 全量 54 | 导航 **N01–N12** |
| 门禁 | Agent `false_success=0` | 只作公开证据；失败要诚实写清 |
| 设备 | 本地 Simulator | 同左 |

**可靠性层次不变：** 模型只提案；Policy / Verifier 确定性兜底；审核 Agent 不能替代写后回读。

## 最近一次公开摘要

源文件：[`docs/reports/live-nav-agent-summary.json`](./reports/live-nav-agent-summary.json)

| 指标 | 值 |
| --- | --- |
| 模式 | `agent` |
| 用例 | 12（N01–N12） |
| 通过 | 7 |
| 失败 | 5 |
| `false_success` | **0** |
| 通过率 | 58.3% |

失败用例（摘要，无 Prompt / 无 Key）：

| ID | 现象（摘要） |
| --- | --- |
| N04 | 模型路由成 MULTI_AGENT 后停住，未落到 `navigate_home` |
| N05 | 澄清等待，未完成公司收藏开航 |
| N07 | 澄清等待，途经+回家未完成 |
| N09 | 生命周期 FAILED（路由仍为 FAST） |
| N10 | 未应用 `set_preference`（偏好仍为 fastest） |

通过用例如 N01/N02 明确开航、N03 未知 POI 诚实失败（`PARTIAL`）、N06 途经、N08/N11/N12 控导/查态等，说明 **真模型输出可以经编译 / 归一化进入受控执行**，且本轮 **没有虚假成功**。

## 如何复跑

仓库根目录配置 `.env`（参考 `.env.example`，**不要提交 Key**），然后：

```bash
cd backend-py
uv run python scripts/run_live_nav_eval.py
```

- 完整原始报告：`backend-py/reports/`（已 gitignore）
- 脱敏公开摘要：`docs/reports/live-nav-agent-summary.json`（可提交）

## 面试怎么讲

1. Fake 54 / `false_success=0` 证明**执行语义与门禁设计**。  
2. 本样本证明**真模型接入路径真实存在**，不是只靠 Fake 演戏。  
3. 真模型通过率会波动；**不要把 7/12 说成产品 SLA**。强调本轮 `false_success=0` 与失败可归因。  
4. 绝不拿外部厂商产品名做对比抬自己。
