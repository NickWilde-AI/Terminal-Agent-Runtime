# Capability 契约

模型只能从注册表白名单中选择工具。写动作必须经过 Policy，成功与否以设备状态回读为准。

内置演示域用于验证智能终端执行闭环；扩展新场景时，优先注册 Capability Schema 与 Device Adapter，无需改写主循环。

演示域与简历四域的对应（脱敏泛化，不是实车接口）：

| 简历能力域 | 仓内演示 |
| --- | --- |
| 车辆设置 | 环境域 `climate.*` / `window.*` |
| 多媒体 | `media.*` |
| 导航 | `navigation.*` |
| 车辆状态 | 通用 `device.get_state` 回读 |

## 当前注册能力（capabilities-v2）

| ID | 域 | 参数 | 说明 |
| --- | --- | --- | --- |
| `device.get_state` | 通用 | `{}` | 读取相关域状态 |
| `climate.set_power` | 环境 | `value: boolean` | 空调电源，不改变舱温 |
| `climate.set_temperature`（别名 `cabin.set_temperature`） | 环境 | `value: 16–30` | 设定温度 ≠ 舱温 |
| `climate.set_fan`（别名 `cabin.set_fan`） | 环境 | `value: 1–3` | 风量 |
| `window.set_position` | 环境 | `window`, `position: 0–100` | 四窗独立开度；`不要开窗` 为硬约束 |
| `media.play` | 多媒体 | `artist` | 占位曲目元数据，无真实音频 |
| `media.pause` | 多媒体 | `{}` | 暂停 |
| `media.set_volume` | 多媒体 | `value: 0–10` | 媒体音量 |
| `navigation.start` | 导航 | `destination` | 本地模拟导航与路线点 |
| `navigation.stop` | 导航 | `{}` | 停止导航 |
| `navigation.set_prompt_enabled` | 导航 | `value: boolean` | 播报开关 ≠ 用户已听到 |
| `navigation.set_volume` / `navigation.set_muted` | 导航 | `value` | 音量 / 静音 |

完整 Schema 以运行时 `GET /api/v1/capabilities` 为准。标准 Tool Calling 使用线名（`.` → `_`），例如 `climate_set_temperature`。

## 结果语义

| 维度 | 含义 |
| --- | --- |
| execution_status | 是否分发 / ACK / APPLIED / UNKNOWN |
| verification_status | 回读是否满足谓词 |
| attribution | THIS_ACTION / EXTERNAL / UNKNOWN |

ACK ≠ APPLIED；数值恰好相等也不等于本任务造成。Three.js 动画只绑定 Simulator Snapshot，不以 Tool ACK 触发几何变化。
