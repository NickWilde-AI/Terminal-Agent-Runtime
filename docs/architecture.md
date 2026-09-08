# 架构

Terminal Agent Runtime（智能终端 Agent Runtime）面向智能终端提供 Agent 执行运行时：模型负责理解与候选动作，Runtime 负责任务状态、策略、工具分发、状态回读与验收。

框架与业务域解耦。仓库内置的环境控制 / 多媒体 / 导航等能力是代表性演示域，用于验证「有副作用、有状态」的闭环；同一套执行思想可映射到 IoT、机器人、云运维、GUI / Coding Agent 与通用 Agent 平台——换 Capability、状态模型与 Policy，不换主循环。详见根目录 README「核心思想：执行层可跨域复用」。

```text
用户输入（语音转写 / 终端 UI / Web）
          │
          ▼
     请求接入与会话
          │
          ▼
     任务理解与路由
   ┌──────┴───────┐
   │              │
  FAST          AGENT
   │       Observe→Plan→Act→Feedback
   └──────┬───────┘
          ▼
 Policy / Permission / Confirmation
          ▼
   Capability Gateway
          ▼
  设备适配层（本地模拟器 / 真实终端 Adapter）
          ▼
     状态回读与任务终态
```

## 核心模块

| 模块 | 路径 | 职责 |
| --- | --- | --- |
| Harness / Runtime | `backend/.../harness` | 有界执行循环、版本、取消、验收 |
| DevicePort | `backend/.../device` | 设备适配边界；Harness / Policy / Verifier 不直接依赖 Simulator |
| Policy | `backend/.../policy` | 白名单、约束、确认门禁 |
| Memory | `backend/.../memory` | 上下文工程与受控长期记忆（本仓为 SQLite 规则版，不是 Milvus） |
| ModelPort | `backend/.../model` | Step / OpenAI-compatible / Fake；规划走标准 Tool Calling |
| Simulator | `backend/.../simulator` | 本地 `DevicePort` 实现：设备真值与故障注入 |
| Eval | `backend/.../eval` | 独立断言与报告 |
| Web | `web/` | 联调工作台 |

## 端云

云端与端侧共用同一套任务 / 工具 / 结果协议。`ModelRouter` 的 `cloud` / `edge` placement 切换模型标签；网络切换时通过 epoch / goal_version 丢弃迟到旧计划。`edge` 在本仓是协议桩，规划阶段返回 `EDGE_UNAVAILABLE`，不是端侧完整 Agent。

本仓库演示数据全部来自本地 Simulator，不含真实用户日志或设备回传。默认模型示例为公开的阶跃星辰 **Step 3.5 Flash**；也可换成 MiniCPM 或其他 OpenAI 兼容模型。
