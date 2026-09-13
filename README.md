# Terminal Agent Runtime

**智能终端 Agent Runtime — 目标可理解，动作可治理，状态可回读，结果可验收**

*From intent to verified action — an open-source Agent execution runtime for real systems.*

[![Python](https://img.shields.io/badge/Python-3.12%20primary-3776AB?logo=python&logoColor=white)](./backend-py/README.md)
[![Java](https://img.shields.io/badge/Java-21%20legacy-ED8B00?logo=openjdk&logoColor=white)](https://openjdk.org/)
[![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.4%20legacy-6DB33F?logo=springboot&logoColor=white)](https://spring.io/projects/spring-boot)
[![React](https://img.shields.io/badge/React-TypeScript-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Docker](https://img.shields.io/badge/Docker-one--click-2496ED?logo=docker&logoColor=white)](#快速开始)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE)

---

## 1. 这是什么

**Terminal Agent Runtime**（中文：**智能终端 Agent Runtime**）是面向真实系统的开源 **Agent 执行运行时**。

它解决的不是「再做一个聊天机器人」，而是把大模型接到真实能力上最难的一段：

- 动作有**副作用**
- 执行后必须**回读状态**
- 过程可**打断 / 改目标**
- 结果必须**可验收、可追溯**

**谁适合用这个仓库**

| 读者 | 你能拿走什么 |
| --- | --- |
| **面试官 / 招聘方** | 可运行的执行层作品：三维证据、取消隔离、`false_success=0` 门禁、导航可信执行；默认 `./start.sh` 即可演示 |
| **厂商 / 平台接入方** | 以 `DomainModule` + `DevicePort` 换自己的能力与设备；模型走 OpenAI 兼容接口；Policy / Verifier 可保留 |
| **同学 / 贡献者** | Fake 评测与单测可本地复现；欢迎新域、用例与文档 PR |

**分工很清楚：**

| 层次 | 职责 | 本仓库 |
| --- | --- | --- |
| 模型层 | 理解、规划、提出候选动作 | 通过 ModelPort 接入；默认可换 |
| 交互层 | Chat / 语音 / IDE / 工作台 | 提供联调工作台；业务 UI 可自建 |
| **执行层** | 任务状态、策略、工具、回读、记忆、评测 | **本项目的中心** |

仓库内置 **智能终端能力域**（环境控制、多媒体、出行导航可信执行、生活服务接口 stub，以及可插拔的 IoT 灯控样例）用于完整跑通闭环；同一套协议可扩展到手机、IoT、机器人、车载、云运维、GUI / Coding Agent、Agent 平台等场景。核心永远是 **Harness + Agent**，域通过 Capability / DevicePort 接入。公开仓以 [`backend-py/`](./backend-py/README.md) **Python 为主实现**（FastAPI / Pydantic / asyncio；评测同看 54 例 / `false_success=0`）；[`backend/`](./backend/) Java 为历史实现与迁移对照。

30 秒上手：

```bash
git clone https://github.com/NickWilde-AI/Terminal-Agent-Runtime.git
cd Terminal-Agent-Runtime
cp .env.example .env          # 填 API Key，或设 DEVICE_AGENT_MODEL_MODE=fake
./start.sh                    # → http://localhost:8080（默认 Python）
```

> **实现分层：** [`backend-py/`](./backend-py/README.md) 为公开主实现；[`backend/`](./backend/) 为 Java 历史对照。`./start.sh` 默认 Python（无需 JDK）；`./start.sh --java` 启动 Java 对照。

---

## 2. 产品闭环：能做什么

```text
用户目标
   │
   ▼
主 Agent 路由
   │
   ├──信息不足──▶ CLARIFY（追问）
   ├──越权/不可做──▶ REJECT
   ├──明确指令──▶ FAST（主 Agent 单次理解 → DIRECT_ACTION）──┐
   │                                                         ▼
   └──复杂目标──▶ 规划 Agent（PlanDraft）                     Policy / 确认
                      │                                      │
                      ▼                                      ▼
                 Plan / Action Preflight（零 LLM）──▶ Runtime 逐步执行 + 写后回读
                                                             │
                                                             ▼
                                              审核 Agent 补查（只读）
                                                             │
                                                             ▼
                                      Verifier 工具 → goal_results
                                      Outcome Aggregator → overall_outcome
                                                             │
                                                             ▼
                                      审核 Agent 解释 / 建议重规划 ──▶ 主 Agent 转达
```

> 首图直接体现：**主 Agent → 规划 Agent → Preflight → Runtime → 审核 Agent**；FAST 跳过规划与审核，不是「不调模型」。终态不由审核 Agent 决定。

**智能终端标杆任务：**

1. **跨域复合目标**：环境舒适度 + 媒体音量 + 导航提示保留，在约束、故障注入与用户改口下，仍执行到可回读终态。  
2. **出行导航可信执行**：明确目的地开航、途经不丢终点、未知 POI 诚实失败、回家/公司收藏、路线偏好、暂停/继续/ETA 查询；「回家途经加油站」禁止收藏开航抢跑。  
3. **生活服务抢域 stub**：显式点外卖进 `life.*` 会话；「去结算」不误判为导航；「顺路咖啡」优先途经点；明确「导航到 X」会打断外卖会话。

### 2.1 为什么需要 Runtime

聊天机器人只负责「说话」；接到真实设备或系统后，还要保证「事情真的做成了」。中间差的这一层，就是 Runtime。

| 如果只有大模型 | 接到真实系统后会出现什么问题 | Runtime 怎么补上 |
| --- | --- | --- |
| 回复一段文字就算完成 | 真正去改温度、部署服务、点按钮，会动到真实状态 | 把「打算做什么」变成受控的工具调用 |
| 失败了再问一句就行 | 系统可能已经改了一半；再发一次可能改两次 | 先核对当前真实状态，再决定要不要继续 |
| 上下文塞得越多越好 | 终端有延迟、费用、隐私和权限限制 | 每一步只注入必要信息，并做权限检查 |
| 模型说「成功了」就信 | 模型可能说错；接口返回成功也不等于事情生效 | 以设备 / 系统回读结果为准做验收 |
| 用户改口，等下一轮再说 | 旧计划可能还在后台继续跑 | 支持取消和改目标，并立刻停掉旧计划 |

一句话：**模型负责想，Runtime 负责在真实世界里安全地做完，并且做得对不对能核对。**  
所以模型可以换、业务可以换，这套「想 → 做 → 核对」的闭环可以复用。

---

## 3. 功能清单：开箱即用的能力

| 模块 | 你能得到什么 |
| --- | --- |
| **路由** | 纯聊天 `CHAT`；明确单目标走 `FAST`（主 Agent 一次理解 / `DIRECT_ACTION`，不进规划与验收）；跨域 / 约束走 `MULTI_AGENT`；信息不足 `CLARIFY`；越权 `REJECT` |
| **三 Agent 协作** | 主 Agent（`TaskSpec`）→ 规划 Agent（`PlanDraft`）→ Plan/Action Preflight → Runtime → 审核 Agent（只读补查）；Verifier 工具算 `goal_results`，Outcome Aggregator 算 `overall_outcome`；写设备只经 Runtime/Policy |
| **可靠性层次（重要）** | **兜底是确定性组件，不是更多模型。** Policy / Preflight 决定能不能写；Verifier 与 Outcome Aggregator 决定算不算成功。审核 Agent 只能解释和建议重规划，**不能**改两级确定性结果，也不能替代写后回读 |
| **任务编译（Task Schema / GoalCompiler）** | 自然语言 → 目标 / 约束 / 完成条件（`goals` / `constraints` / `criteria`）；模型候选必须覆盖编译结果，见 `GoalCompilerCoverageTest` |
| **有界执行循环** | Observe → Plan → Policy → Act → Verify；步数与时间预算有上限，避免空转 |
| **三维证据** | `execution_status` / `verification_status` / `attribution` 分离；ACK ≠ APPLIED；数值碰巧相等 ≠ 本任务造成 |
| **UNKNOWN 对账** | 响应丢失先读状态再决策，不盲目重发写动作 |
| **策略门禁** | 能力白名单、参数范围、领域约束、敏感动作确认等待 |
| **域可插拔** | `DomainModule` 注册能力包；`DevicePort` 适配真实终端；内置 `terminal` + `iot` 两域样例 |
| **用户介入** | 取消、运行中改目标、澄清回答、批准 / 拒绝 |
| **上下文工程** | 每步最小注入：当前目标、约束、相关状态、必要对话 |
| **受控长期记忆** | 偏好写入门禁、隐私拦截、冲突仲裁、可审计；可参与默认值建议 |
| **端云协议** | 统一 `ModelPort`；`cloud` / `edge` placement；epoch / goal_version 丢弃迟到旧计划 |
| **模型适配** | 默认阶跃 Step；`openai_compatible` 走标准 Tool Calling（`tools` + `tool_calls` + `role=tool`）；CI 用 `fake`；主 Agent 任务编译解析失败不降级 Fake（Planner/Auditor 解析失败可记 `parse_fallback` 并确定性兜底） |
| **设备模拟器** | 本地真值状态、延迟、故障注入、外部扰动；导航 POI 搜索失败诚实；生活服务仅会话占位 |
| **3D 工作台** | React Three Fiber 程序化车辆；车窗/空调气流/媒体频谱/导航路线只绑定 Simulator Snapshot |
| **可观测** | Run 事件流（SSE）、只读回放、Trace 落盘；工作台实时展示 |
| **评测** | Fake 业务种子 **54** 例（含 **N01–N12** 出行导航与 **IOT01–IOT02** IoT 灯控）；`agent` / `baseline` 对照；门禁关注 `false_success=0`；断言独立于 Planner |
| **工作台** | 任务、设备、介入、记忆、故障、回放、评测一站式 |
| **持久化** | SQLite 任务 / 事件；支持重启后的恢复路径 |
| **一键部署** | `./start.sh`：默认 Docker Compose + **Python** Runtime；`--local` 本地单进程；`--java` 历史对照；工作台 + API |

### 设计原则

1. **领域可插拔** — 新增能力优先加 `DomainModule` + DevicePort Adapter，不重写 Harness / Agent 主循环  
2. **安全边界清晰** — Policy 是确定性代码；模型不能发明未注册工具  
3. **验收独立于叙事** — 成败看状态谓词与证据，不看模型自我总结；多 Agent 协作不等于多层模型兜底  
4. **内置能力 ≠ 框架边界** — 内置智能终端能力用于验证闭环；执行层面向广泛真实系统  
5. **模型可替换** — 换网关与模型 ID 即可，Runtime 契约不变  

### 本仓库边界

本仓库是**独立开源实现**，用来落地「有副作用系统」上的 Agent 执行语义。不含任何商业产品源码、内部接口、真实用户数据或设备日志；联调状态全部由本地模拟器生成。

| 本仓库包含 | 本仓库刻意不做 |
| --- | --- |
| 自研 Harness、FAST / MULTI_AGENT、写后回读、取消隔离、评测 | 生产级 MCP Gateway |
| 标准 Tool Calling（`tools` / `tool_calls` / `role=tool`） | 向量数据库记忆（如 Milvus） |
| DevicePort + 本地 Simulator（导航可信执行 + life stub） | 文档型 Agentic RAG |
| 受控结构化长期记忆（SQLite） | 真实设备 SDK / 生产网关 / 真实外卖业务 |
| `edge` placement 返回 `EDGE_UNAVAILABLE` | 端侧完整 Agent / 地图算法引擎 |

默认云端模型为 **阶跃星辰 Step 3.5 Flash**：公开模型，工具调用 / Agent 规划比较稳。国产模型里 **MiniCPM** 同样适合这类闭环。两者都走 OpenAI 兼容接口，改环境变量即可切换；`step-3.7-flash` 如需使用也一样，不绑定单一厂商。

---

## 4. 适用谁：怎么扩展到你的场景

本项目开源给所有需要「让 Agent 操作真实系统」的开发者与团队。

| 场景 | 状态从哪来 | 动作是什么 | 怎样算真正完成 |
| --- | --- | --- | --- |
| **智能终端**（仓库内置） | 环境、媒体、导航、生活服务会话、IoT 灯控等设备真值 | 设定、开航/途经、多域协同、life stub、灯开关 | 回读满足目标与约束；导航失败诚实 |
| **手机 / 平板 / 穿戴** | 系统设置、通知、应用状态 | 端侧工具与快捷操作 | 系统状态与权限边界一致 |
| **IoT / 智能家居** | 灯、锁、传感、网关 | 开合、模式、场景联动 | 设备上报与目标谓词一致 |
| **具身机器人** | 位姿、夹爪、传感器 | 移动、抓取、放置 | 感知回读，而不只看指令回执 |
| **云资源 / 发布 / DevOps** | 版本、健康、环境 | 部署、扩缩、回滚 | 健康与目标一致，而非仅接口成功 |
| **IT 运维** | 告警、主机、配置 | 重启、切流、变更 | 指标恢复；高危操作需确认 |
| **办公自动化 / RPA** | 表单、单据、审批流 | 填写、提交、流转 | 业务系统落库状态可核对 |
| **GUI Agent** | 界面树 / 截图 / 控件 | 点击、输入、滑动 | 界面回到预期，避免误操作 |
| **Coding Agent** | 仓库、测试、终端输出 | 改文件、跑命令、提交 | 测试与目标一致；禁区由策略拦住 |
| **Agent 平台 / 工具网关** | 会话、租户、工具目录 | 插件、MCP、内部 API | 全链路可观测、可评测、可治理 |

无论场景叫什么，执行层重复出现的都是：路由、有界循环、策略门禁、状态回读、介入与取消、记忆与评测。

### 4.1 扩展示例：接到发布系统

二次开发时，通常只需替换「能力与状态」，主循环可保持不变：

```text
目标：将测试环境升级到 v2，保留数据，不影响生产
观察：当前版本、环境、健康检查、在途变更
能力：查询发布、执行部署、健康检查、回滚
策略：禁止操作生产；禁止破坏性删库
闭环：部署 → 回读健康 → 成功或回滚 → 按真实状态回复
```

关键不变量：

- **回执 ≠ 生效** — 接口成功不能代替状态验收  
- **约束先于执行** — 危险动作必须先过 Policy / 确认  
- **目标可中途变更** — 用户改口后，旧计划必须停止  

### 4.2 扩展步骤

1. 用智能终端能力跑通 `./start.sh`，理解路由 → 执行 → 回读 → 评测  
2. 为新域注册 Capability Schema，实现 Adapter（读状态 / 写动作）  
3. 编写领域 Policy 与验收谓词（什么允许做、怎样算完成）  
4. 按需切换 ModelPort 后端（任意 OpenAI-compatible 网关）  
5. 用 Eval 用例锁住回归，避免「看起来成功、实际未生效」  

当前仓库完整落地智能终端能力闭环，并提供第二域 IoT 灯控样例证明可插拔；上表是同一执行思想可应用的方向。欢迎贡献新 DomainModule / DevicePort 与评测用例。

---

## 5. 快速开始：怎么用

### 5.1 环境要求

| 方式 | 要求 |
| --- | --- |
| **推荐：Docker 一键** | Docker Desktop（或兼容 Engine + Compose）；默认 **Python** Runtime，**无需 JDK** |
| **本地单进程（默认 Python）** | Python 3.12 + [`uv`](https://github.com/astral-sh/uv)（推荐）或 venv；Node 18+（首次构建前端） |
| **本地 / Docker Java 对照** | `./start.sh --java`；需要 Java 21、Maven 3.9+ |

### 5.2 安装与配置

```bash
git clone https://github.com/NickWilde-AI/Terminal-Agent-Runtime.git
cd Terminal-Agent-Runtime
cp .env.example .env
```

编辑 `.env`（默认对接阶跃 Step OpenAI-compatible 接口）：

| 变量 | 默认 / 示例 | 说明 |
| --- | --- | --- |
| `DEVICE_AGENT_MODEL_MODE` | `openai_compatible` | 或 `fake`（无密钥跑通闭环） |
| `DEVICE_AGENT_MODEL_BASE_URL` | `https://api.stepfun.com/v1` | 任意兼容网关 |
| `DEVICE_AGENT_MODEL_API_KEY` | （必填，除非 fake） | API 密钥，勿提交仓库 |
| `DEVICE_AGENT_MODEL_ID` | `step-3.5-flash` | 默认云端模型；也可换成 MiniCPM 或 `step-3.7-flash` 等兼容模型名 |
| `DEVICE_AGENT_MODEL_EDGE_ID` | `step-edge-stub` | 端侧模型占位 |
| `DEVICE_AGENT_MODEL_PLACEMENT` | `cloud` | `cloud` / `edge` |
| `DEVICE_AGENT_PERSISTENCE` | `sqlite` | 持久化后端 |
| `DEVICE_AGENT_SQLITE_PATH` | `./data/harness.db` | SQLite 路径 |
| `DEVICE_AGENT_EVENT_LOG_DIR` | `./data/events` | 事件日志目录 |
| `DEVICE_AGENT_REQUIRE_CONFIRMATION` | `false` | `true` 时敏感写动作需批准 |
| `DEVICE_AGENT_WEB_DIST` | （本地模式自动设置） | 工作台静态资源目录 |

更多预设见 [`configs/presets/`](./configs/presets/)。

### 5.3 一键启动

```bash
./start.sh
```

`./start.sh` 行为：

| 模式 | 触发条件 | 结果 |
| --- | --- | --- |
| Docker + Python（默认） | `./start.sh` / `--docker` / `--python` | Compose 拉起工作台 + **Python** Runtime |
| Docker + Java 对照 | `./start.sh --java` | Compose 使用 `docker-compose.java.yml` |
| 本地 + Python（默认） | `./start.sh --local` | 单进程 `:8080` = 工作台 + Python API（**无需 JDK**） |
| 本地 + Java 对照 | `./start.sh --local --java` | 单进程 Java jar |

打开 http://localhost:8080/api/v1/meta ，字段 `runtime` 应为 `"python"`（或对照模式下为 `"java"`）。

| URL | 用途 |
| --- | --- |
| http://localhost:8080 | 联调工作台 |
| http://localhost:8080/api/v1/meta | 实例元信息（含 `runtime`）与模型配置 |
| http://localhost:8080/api/v1/capabilities | 当前能力注册表 |
| http://localhost:8080/api/v1/device/state | 当前设备 / 模拟器状态 |

常用命令：

```bash
./start.sh --status              # 查看是否可用（含 runtime）
./start.sh --stop                # 停止 Docker / 本地进程
./scripts/smoke_api.sh           # API 冒烟
FORCE_REBUILD=1 ./start.sh       # 强制重建
./start.sh --local               # 本地 Python
./start.sh --local --java        # 本地 Java 对照
./start.sh --java                # Docker Java 对照
./start.sh --python              # 显式 Python（同默认）
```

无密钥快速体验：

```bash
DEVICE_AGENT_MODEL_MODE=fake ./start.sh
```

首次启动会构建依赖与镜像，可能需要几分钟；之后重启会快很多。

---

## 6. 工作台：打开后怎么玩

服务启动成功后，用浏览器打开下面地址：

```text
http://localhost:8080
```

这就是 Web 工作台：

- **左侧**：输入自然语言任务并发送  
- **右侧**：查看当前设备状态、执行步骤和结果  

建议按下面顺序点一遍。每一步都写清「你做什么」和「正常时该看到什么」：

| 步骤 | 你在页面上做什么 | 正常时你会看到什么 |
| --- | --- | --- |
| 1. 先试一句简单指令 | 输入类似「把温度设为 23 度」，点发送 | 任务很快结束；右侧温度变成 23；过程里能看到已经执行并核对过 |
| 2. 再试出行导航 | 输入「导航到东方明珠」，再试「加个途经点星巴克」 | 开航后目的地可见；途经点追加后终点仍在；未知地名应诚实失败 |
| 3. 再试一句复杂目标 | 输入需要同时改环境、媒体、导航等多件事的长句，或「回家途经加油站」 | 系统会分多步做；收藏开航不会抢走途经信号 |
| 4. 故意制造异常 | 用「故障注入」选择：响应丢失、延迟生效、读取失败等 | 系统会先核对真实状态，再决定要不要继续；不应不管结果重复乱改 |
| 5. 中途改主意 | 任务还在跑时点「取消」，或输入「改成 25 度」 | 旧任务停住；新目标接管；不会继续执行已经作废的计划 |
| 6. 试试生活服务 stub | 输入「点外卖咖啡」，再输入「导航到东方明珠」 | 先进入 life 会话占位；开航后会话被打断关闭（不宣称真实下单） |
| 7. 试试长期记忆 | 输入「记住我喜欢温度 24 度」，再开一个相关任务 | 记忆列表出现这条偏好；后续任务可把它当默认建议，但仍受安全策略约束 |
| 8. 跑一遍评测 | 点工作台里的评测，或用下面的命令 | Fake 约 54 例业务种子；关注 `false_success=0`；可对照 agent / baseline |

工作台的作用很简单：证明系统**不只会聊天**，而是**真的改到了状态**，并且异常、取消、改口也能兜住。

更细的 HTTP 调用见 [examples/curl_demos.md](./examples/curl_demos.md)。

```bash
# 清空演示环境，从头开始
curl -X POST 'http://localhost:8080/api/v1/experiment/reset'

# 发一句简单任务
curl -X POST 'http://localhost:8080/api/v1/runs' \
  -H 'Content-Type: application/json' \
  -d '{"text":"把温度设为 23 度","requestId":"demo-1","sessionId":"demo"}'

# 跑评测并查看最近报告
curl -X POST 'http://localhost:8080/api/v1/evals/run?mode=agent'
curl -X POST 'http://localhost:8080/api/v1/evals/run?mode=baseline'
curl -s 'http://localhost:8080/api/v1/evals/last'
```

---

## 7. 模型适配：默认 Step，主流模型可切换

本项目是 **Agent 执行 Runtime**。默认示例使用 **阶跃星辰 Step 3.5 Flash**，因为它在 Tool Calling / Agent 规划上比较稳；国产模型里 **MiniCPM** 同样适合这类「规划 → 工具 → 回读」闭环。Runtime **不绑定**单一厂商。

只要模型服务提供 **OpenAI 兼容** 的对话接口（`/v1/chat/completions`），就可以接入。切换时只改 `.env` 里三项，**不用改业务代码**：

1. `DEVICE_AGENT_MODEL_BASE_URL` — 接口地址  
2. `DEVICE_AGENT_MODEL_API_KEY` — 密钥  
3. `DEVICE_AGENT_MODEL_ID` — 模型名  

| 厂商 | 怎么配 | 接口地址示例 | 模型名示例 |
| --- | --- | --- | --- |
| 阶跃 Step（默认） | 直接填官方 Key | `https://api.stepfun.com/v1` | `step-3.5-flash` |
| 面壁 MiniCPM | 自托管或走兼容网关 | vLLM / Ollama / 云厂商给出的 `/v1` | 以托管模型名为准，如 `MiniCPM4` |
| 通义千问 | 用阿里云百炼「兼容模式」 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| DeepSeek | 直接填官方 Key | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | 直接填官方 Key | `https://api.openai.com/v1` | `gpt-4o` |
| 月之暗面 Kimi | 直接填官方 Key | `https://api.moonshot.cn/v1` | `moonshot-v1-128k` |
| 智谱 GLM | 直接填官方 Key | `https://open.bigmodel.cn/api/paas/v4` | `glm-4` |
| 豆包 / 火山方舟 | 用控制台给出的兼容地址 | 以控制台为准 | 以控制台为准 |
| Claude | 官方协议不同，需兼容网关中转 | 填网关提供的兼容地址 | 填网关映射的模型名 |
| Ollama（本地） | 本机先拉起模型 | `http://127.0.0.1:11434/v1` | 本地模型名，如 `qwen2.5:14b` |
| Fake | 无密钥演示 / CI | 不需要 | 设 `DEVICE_AGENT_MODEL_MODE=fake` |

**MiniCPM 示例（自托管）：**

```bash
DEVICE_AGENT_MODEL_MODE=openai_compatible
DEVICE_AGENT_MODEL_BASE_URL=http://127.0.0.1:8000/v1
DEVICE_AGENT_MODEL_API_KEY=
DEVICE_AGENT_MODEL_ID=MiniCPM4
```

**千问示例：**

```bash
DEVICE_AGENT_MODEL_MODE=openai_compatible
DEVICE_AGENT_MODEL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DEVICE_AGENT_MODEL_API_KEY=你的百炼Key
DEVICE_AGENT_MODEL_ID=qwen-plus
```

**DeepSeek 示例：**

```bash
DEVICE_AGENT_MODEL_MODE=openai_compatible
DEVICE_AGENT_MODEL_BASE_URL=https://api.deepseek.com/v1
DEVICE_AGENT_MODEL_API_KEY=你的DeepSeekKey
DEVICE_AGENT_MODEL_ID=deepseek-chat
```

**OpenAI 示例：**

```bash
DEVICE_AGENT_MODEL_MODE=openai_compatible
DEVICE_AGENT_MODEL_BASE_URL=https://api.openai.com/v1
DEVICE_AGENT_MODEL_API_KEY=你的OpenAIKey
DEVICE_AGENT_MODEL_ID=gpt-4o
```

**本地 Ollama 示例：**

```bash
DEVICE_AGENT_MODEL_MODE=openai_compatible
DEVICE_AGENT_MODEL_BASE_URL=http://127.0.0.1:11434/v1
DEVICE_AGENT_MODEL_API_KEY=ollama
DEVICE_AGENT_MODEL_ID=qwen2.5:14b
```

补充说明：

- 具体模型名、计费和工具调用能力，以各厂商控制台为准；上表只是常用示例。  
- 端侧 / 云端切换：`DEVICE_AGENT_MODEL_PLACEMENT=cloud` 或 `edge`，端侧模型名用 `DEVICE_AGENT_MODEL_EDGE_ID`。  
- 更多片段见 [`configs/presets/`](./configs/presets/)。

---

## 8. API 一览

基础路径：`/api/v1`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/meta` | 产品名、模型、placement、持久化等 |
| GET | `/capabilities` | 工具 / Capability 注册表 |
| GET | `/device/state` | 当前状态快照 |
| POST | `/runs` | 创建任务（可异步执行） |
| GET | `/runs` | 任务列表 |
| GET | `/runs/{id}` | 任务详情 |
| GET | `/runs/{id}/events` | 事件增量（JSON） |
| GET | `/runs/{id}/events/stream` | 事件 SSE |
| GET | `/device/state/stream` | 设备状态 SSE |
| GET | `/runs/{id}/replay` | 只读回放 |
| POST | `/runs/{id}/cancel` | 取消 |
| POST | `/runs/{id}/clarify` | 澄清回答 |
| POST | `/runs/{id}/intervene` | 运行中改目标 |
| POST | `/runs/{id}/answer` | 确认批准 / 拒绝 |
| GET/POST/DELETE | `/memory` | 受控长期记忆 |
| POST | `/model/placement` | 切换 `cloud` / `edge` |
| POST | `/experiment/reset` | 先取消同设备活动任务，再重置模拟器 |
| POST | `/experiment/fault` | 故障注入 |
| POST | `/experiment/external-change` | 外部状态扰动 |
| POST | `/evals/run` | 跑评测 |
| GET | `/evals/last` | 最近评测报告 |

完整说明见 [docs/api.md](./docs/api.md)。

---

## 9. 评测与测试

评测答案**不依赖模型临场发挥的「自我总结」**：用例与期望结果独立存放，用来检查「有没有真的做对」。

```bash
# 服务已启动时
curl -X POST 'http://localhost:8080/api/v1/evals/run?mode=agent'
curl -X POST 'http://localhost:8080/api/v1/evals/run?mode=baseline'
curl -s 'http://localhost:8080/api/v1/evals/last'

# 贡献者本地单测（默认 Python）
cd backend-py && source .venv/bin/activate && DEVICE_AGENT_MODEL_MODE=fake pytest tests/ -q
# 可选：Java 历史实现对照
cd backend && mvn test
```

覆盖面包括：简单指令、复杂多目标、故障、策略拒绝、取消与改目标、记忆规则，以及 **出行导航可信执行（N01–N12）**。  
当前 Fake 评测基线为 **54** 例业务种子（`EvalCatalog`），门禁关注 `false_success=0`。注意：本地单测方法数（`pytest` / 可选 `mvn test`）是另一维度，勿与 54 混说。

两种评测模式：

- `agent`：按真实闭环一步步做完再验收  
- `baseline`：先编译再一次性展开，用来对照「有没有状态反馈循环」带来的差异  

**对照读报告时注意：** 默认 Python 路径写到 `backend-py/reports/last-agent.json` 与 `last-baseline.json`（Java 对照仍在 `backend/reports/`）。两份报告必须同一 `EvalCatalog` 版本才可横比通过率。当前 Fake 下 Agent 追求高通过且 `false_success=0`；Baseline 作为「无状态反馈循环」对照，通过率更低、允许出现 `false_success`，**不能**用 Baseline 通过率否定 Agent 门禁。若两份报告 `total` 不一致，先重跑两种模式再对照。

可选：**真实模型导航抽检**（N01–N12）见 [docs/live-model-eval.md](./docs/live-model-eval.md)；与 Fake 54 门禁分开读，不混算。

详见 [docs/evaluation.md](./docs/evaluation.md)。能力清单见 [docs/capabilities.md](./docs/capabilities.md)（`capabilities-v4`）。扩展新域见 [docs/extending.md](./docs/extending.md)。

---

## 10. 项目结构

```text
.
├── README.md                 # 对外主文档（本文件）
├── LICENSE                   # Apache-2.0
├── .env.example              # 环境变量模板
├── start.sh                  # 一键启动（停止：./start.sh --stop）
├── scripts/
│   ├── start.sh              # Docker / 本地统一入口
│   ├── smoke_api.sh
│   ├── run_backend.sh        # 贡献者热开发（可选）
│   └── run_web.sh
├── deploy/compose/           # Docker Compose（默认 Python；*.java.yml 为对照）
├── configs/presets/          # 模型预设（如 Step）
├── docs/                     # 架构 / Capability / API / 评测
├── examples/                 # curl 示例
├── backend-py/               # Python 主实现（FastAPI Runtime；见 backend-py/README.md）
├── backend/                  # Java 21 · Spring Boot（历史实现 / --java 对照）
│   └── src/main/java/com/deviceagent/
│       ├── api/              # HTTP API
│       ├── device/           # DevicePort（模拟器 / 真实设备适配边界）
│       ├── harness/          # 任务状态机与执行循环
│       ├── policy/           # 策略与确认
│       ├── capability/       # 工具注册与效应
│       ├── memory/           # 上下文与受控长期记忆
│       ├── model/            # ModelPort / Router / Adapter
│       ├── simulator/        # 本地设备模拟与故障注入
│       ├── eval/             # 独立评测
│       └── store/            # 内存 / SQLite 持久化
└── web/                      # React + TypeScript 联调工作台
```

---

## 11. 文档索引

| 文档 | 内容 |
| --- | --- |
| [docs/architecture.md](./docs/architecture.md) | 总体架构与数据流 |
| [docs/capabilities.md](./docs/capabilities.md) | 工具 / Capability 契约 |
| [docs/extending.md](./docs/extending.md) | 扩展新域 / 新能力（DomainModule + DevicePort） |
| [docs/api.md](./docs/api.md) | HTTP API 详解 |
| [docs/evaluation.md](./docs/evaluation.md) | 评测与回归 |
| [backend-py/README.md](./backend-py/README.md) | Python 主实现（Runtime / 评测 / API） |
| [examples/curl_demos.md](./examples/curl_demos.md) | curl 演示 |
| [configs/README.md](./configs/README.md) | 配置预设说明 |
| [.env.example](./.env.example) | 环境变量模板 |

---

## 12. 安全

- 不要将 `.env` 与真实密钥提交到仓库  
- 本仓库不含真实用户数据、设备日志或内部接口；演示状态由本地模拟器生成  
- 长期记忆默认拦截敏感写入；历史回放只读，不写设备  
- 内置 Simulator 仅用于本地联调；对接真实系统需自建 Adapter，并遵守设备 / 平台侧权限与安全策略  
- 本框架编排的是可治理的终端与系统能力，**不**承担运动控制或其他高危执行器控制器职责  

---

## 13. Contributing

欢迎通过 GitHub Issues / Pull Requests 贡献：

- 新域 Capability Adapter 与验收用例  
- 故障注入场景、评测样本、文档与示例  
- Bug 修复、可观测性与性能改进  

建议贡献前本地跑通：

```bash
./start.sh --local
curl -s http://localhost:8080/api/v1/meta   # 应含 "runtime":"python"
./scripts/smoke_api.sh
cd backend-py && source .venv/bin/activate && DEVICE_AGENT_MODEL_MODE=fake pytest tests/ -q
```

---

## License

[Apache License 2.0](./LICENSE)
