# Capability 契约

模型只能从注册表白名单中选择工具。写动作必须经过 Policy，成功与否以设备状态回读为准。

**核心不变：** Harness + Agent。业务域通过 `DomainModule` 注册 Capability，通过 `DevicePort` 接入真实终端 / 模拟器，无需改写主循环。扩展步骤见 [extending.md](./extending.md)。

内置能力与产品四域的对应（脱敏泛化，不是某一厂商专有接口）：

| 产品能力域 | 仓内能力 |
| --- | --- |
| 车辆控制 / 环境控制 | `climate.*` / `window.*` |
| 多媒体 | `media.*` |
| 出行导航 | `navigation.*`（可信执行，不是地图算法） |
| 生活服务 | `life.*`（仅接口 stub / 会话占位，不实现真实点单） |
| IoT 样例（第二域） | `iot.light.set_power` |

「设备状态」是执行层回读真值的技术概念，贯穿各域。通用读取能力：`device.get_state`。

当前版本：**capabilities-v4**（由 `TerminalDomainModule` + `IotDomainModule` 组装）。

## 主要注册能力

| ID | 域 | 参数 | 说明 |
| --- | --- | --- | --- |
| `device.get_state` | 通用 | `{}` | 读取相关域状态 |
| `climate.*` / `window.*` | 环境 | 见运行时 Schema | 温度、风量、车窗 |
| `media.*` | 多媒体 | 见运行时 Schema | 播放 / 暂停 / 音量 |
| `navigation.start` … `query_*` | 导航 | 见运行时 Schema | 开航、途经、控导、查态、偏好、收藏 |
| `life.*` | 生活服务 | 见运行时 Schema | stub + 会话占位 |
| `iot.light.set_power` | IOT | `value: boolean` | 第二域灯控样例 |

完整 Schema 以运行时 `GET /api/v1/capabilities` 为准。标准 Tool Calling 使用线名（`.` → `_`）。

## 抢域约定（生活服务）

- 显式点外卖 / 美团等 → 进 `life.*`
- 「顺路咖啡」等途经信号 → 优先 `navigation.add_waypoint`
- 「去结算」→ `life.go_to_checkout`，禁止当成导航目的地
- 明确导航开航 → 打断并关闭外卖会话

## 结果语义

| 维度 | 含义 |
| --- | --- |
| execution_status | 是否分发 / ACK / APPLIED / UNKNOWN |
| verification_status | 回读是否满足谓词 |
| attribution | THIS_ACTION / EXTERNAL / UNKNOWN |

ACK ≠ APPLIED；数值恰好相等也不等于本任务造成。
