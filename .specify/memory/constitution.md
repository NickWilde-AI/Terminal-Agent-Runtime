# Terminal Agent Runtime Constitution

> **本机完整宪法（含 private 资料边界与面试分层）：** [`private/docs/15-项目宪法.md`](../../private/docs/15-项目宪法.md)
>
> 若该文件存在，Agent MUST 同时遵守且**以它为准**。`private/` 被外层 `.gitignore` 忽略，MUST NEVER 提交到开源仓。
> 以下条款是开源仓可公开执行的治理子集，供 Spec Kit 在无 private 副本时仍能运行。

## Core Principles

### I. Runtime 执行闭环优先

本仓库是 **Agent 执行运行时**，不是聊天机器人、不是模型训练、不是语音底座。

- MUST 把自然语言目标编译为可执行契约（目标 / 约束 / 完成条件），再进入观察 → 规划 → 策略 → 动作 → 回读。
- MUST 保持分工：模型只提候选；Harness / Policy / Verifier 做校验、授权、分发与终态判定。
- MUST NOT 用一次 Function Calling 或一段模型自我总结代替任务完成。
- 明确单目标走 FAST（主 Agent 单次理解 / `DIRECT_ACTION`，跳过规划与审核）；跨域或带约束走 MULTI_AGENT；信息不足 CLARIFY；越权或无能力 REJECT。
- FAST MUST NOT 被写成「完全免大模型调用」。

**Rationale：** 接到真实系统后，动作有副作用；成败只能由受控执行与状态回读证明。

### II. 三维证据验收，禁止虚假成功（NON-NEGOTIABLE）

动作证据 MUST 三维分离，禁止互相替代：

| 维度 | 回答的问题 | 禁止用法 |
| --- | --- | --- |
| `execution_status` | 是否分发 / ACK / APPLIED / UNKNOWN | 用 ACK 宣称已生效 |
| `verification_status` | 回读谓词是否满足 | 用模型「成功了」当验收 |
| `attribution` | 是否可归因于本任务 | 用数值碰巧相等当本动作造成 |

硬规则：

- ACK ≠ APPLIED；回读未变 ≠ NOT_APPLIED；UNKNOWN ≠ 失败。
- UNKNOWN 或响应丢失时 MUST 先读状态再决策，MUST NOT 盲目重发写动作。
- 评测门禁 MUST 关注 `false_success=0`；MUST NOT 为保住总分而改正确答案或把断言泄漏进 Planner。
- 评测答案 MUST 独立于 Planner，不进入模型 Prompt。
- Fake 业务种子规模以现行 `EvalCatalog` 为准（当前 **54** 例，含导航 N01–N12 与 IoT 样例）；MUST NOT 与 `mvn test` 的 JUnit 方法数混说。
- Baseline 允许更低通过率甚至出现 `false_success`；MUST NOT 用 Baseline 通过率否定 Agent 门禁。

**Rationale：** 虚假成功会把错误执行送进真实世界；这是本项目不可妥协的安全底线。

### III. Policy 是确定性代码边界

- Policy / 权限 / 确认门禁 MUST 是确定性代码，MUST NOT 交给模型临场发挥。
- 模型 MUST 只能选择已注册 Capability；未知工具或非法参数 MUST NOT 执行。
- 写设备 MUST 只经 Runtime / Policy；终态 MUST 只由 Verifier 判定。
- 受控长期记忆可以提供默认值与建议，MUST NOT 越过 Policy、确认门禁或用户显式约束。
- 敏感信息（隐私、支付等）默认 MUST NOT 入长期记忆，或必须脱敏；每条记忆 MUST 可溯源、可查看、可删除。
- 用户取消 / 改目标 MUST 立即阻止旧计划新分发；迟到的旧结果 MUST NOT 覆盖新 `goal_version` 或重新打开终态。
- 取消不依赖模型返回；已分发动作可能仍生效，MUST 如实展示，不假装回滚。

**Rationale：** 安全边界若可被模型改写，白名单与确认链就失效。

### IV. 域可插拔，主循环稳定

- 新增能力优先加 `DomainModule` + `DevicePort` Adapter + 领域 Policy + 验收谓词，MUST NOT 重写 Harness / Agent 主循环。
- 内置智能终端能力（环境、多媒体、出行导航可信执行、生活服务 stub、IoT 灯控样例）用于验证闭环；MUST NOT 把内置域写成框架边界。
- 出行导航：明确目的地开航、途经不丢终点、未知 POI 诚实失败；「回家途经加油站」MUST NOT 被收藏开航抢跑。
- 生活服务仅会话 stub：显式点外卖进 `life.*`；「去结算」MUST NOT 误判为导航；明确「导航到 X」可打断外卖会话。MUST NOT 宣称真实下单。
- 一次只分发一个具体写动作；未分发计划在回读或外部变化后 MUST 重新检查。
- 循环 MUST 有步数与时间预算，禁止空转。

**Rationale：** 执行语义可复用；业务域应该可替换，而不是复制第二套 Runtime。

### V. 诚实范围与可替换模型

- 模型经统一 `ModelPort` 接入；默认 OpenAI 兼容接口可切换，Runtime 契约 MUST 保持不变。
- `DEVICE_AGENT_MODEL_MODE=fake` 仅用于可复现测试与无密钥演示。真实 API 不可用、JSON/Schema 解析失败时 MUST NOT 降级 Fake 后仍计为 `openai_compatible` 成功。
- 主 Agent 任务编译解析失败 MUST NOT 降级 Fake；Planner / Reviewer 解析失败可记 `parse_fallback` 并做确定性兜底。
- `edge` placement 当前返回 `EDGE_UNAVAILABLE` 时，MUST NOT 把「离线端侧 Agent」写成已实现。
- 模拟器状态、故障注入、网页回放是仿真证据。MUST NOT 宣称实车温度、真实听感、车端协议、生产 SLA 或量产能力已验证。
- MUST NOT 把未实现能力（生产级 MCP Gateway、向量库记忆、真实设备 SDK、真实外卖、地图算法引擎、端侧完整 Agent）写成已完成。
- 公开对照项目仅作行业参考，MUST NOT 写成个人 POC 底座或本仓库依赖。

**Rationale：** 开源可信度建立在可核对的边界上；夸大等于制造假证据。

## 仓库与资料边界

| 位置 | MUST 用于 | MUST NOT 用于 |
| --- | --- | --- |
| 外层代码仓 | Harness、评测、工作台、脱敏 README | 凭据、面试稿、公司源码、真实设备日志 |
| `private/`（若存在） | 本地实施权威、调研、面试材料 | 提交到外层 git 远程 |
| `.env` / `*.pem` | 本机密钥 | 入库 |

网页工作台的设备状态 MUST 绑定后端 / Simulator Snapshot，前端 MUST NOT 乐观显示「已经改成功」。

本地 `private/` 内的面试分层、历史快照与 archive 禁令，以完整宪法为准；开源仓文档 MUST NOT 混入求职叙事。

## 质量门禁与工作流

- 行为变化 MUST 有可复现证据：契约测试、Fake eval、或真实 API 报告（标明模式）。
- 导航 / 策略 / 回读 / 取消隔离相关改动 MUST 保持 `false_success=0`。
- 发现契约矛盾时 MUST 先定位权威文档，修正后同步引用；MUST NOT 静默扩大能力目录或改写用户目标。
- 主流程必须真实跑通；没有验证的生产细节 MUST NOT 假装已实现。
- 新功能优先走 `/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement` → `/speckit-converge`。

## Governance

本宪法高于习惯性实现与口头约定。本机若存在 `private/docs/15-项目宪法.md`，以其为最高本地权威。面试与对外叙事怎么写，以 `private/docs/14-文档编写规则.md` 为准，本文不替代其分层规则。

**修订程序**

1. 变更 MUST 写明：改了哪条原则、为什么、对代码 / 文档的迁移影响。
2. 原则删除或重新定义 → MAJOR；新增原则或实质扩展 → MINOR；措辞澄清 → PATCH。
3. 修订后 MUST 同步本文件与 `private/docs/15-项目宪法.md`（若存在）。
4. `LAST_AMENDED_DATE` MUST 更新为修订当日（ISO `YYYY-MM-DD`）。

**合规审查**

- 每次涉及执行语义、评测或对外表述的改动，作者与 Agent MUST 自检原则 I–V。
- 复杂新能力开工前 MUST 能回答：验收谓词是什么、Policy 拦什么、失败时如何避免虚假成功。

**Version**: 1.0.1 | **Ratified**: 2026-09-11 | **Last Amended**: 2026-09-11
