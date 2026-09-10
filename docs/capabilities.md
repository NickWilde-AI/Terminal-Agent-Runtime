# Capability 契约

模型只能从注册表白名单中选择工具。写动作必须经过 Policy，成功与否以设备状态回读为准。

内置演示域用于验证智能终端执行闭环；扩展新场景时，优先注册 Capability Schema 与 Device Adapter，无需改写主循环。

演示域与产品四域的对应（脱敏泛化，不是实车接口）：

| 产品能力域 | 仓内演示 |
| --- | --- |
| 车辆控制 | 环境域 `climate.*` / `window.*` |
| 多媒体 | `media.*` |
| 出行导航 | `navigation.*`（可信执行，不是地图算法） |
| 生活服务 | `life.*`（仅接口 stub / 会话占位，不实现真实点单） |

「车辆状态」是执行层回读真值的技术概念，贯穿各域，**不**单独列为产品第四域。通用读取能力：`device.get_state`。

## 当前注册能力（capabilities-v3）

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
| `navigation.start` | 导航 | `destination` | 明确目的地开航；未知 POI 诚实失败 |
| `navigation.stop` / `pause` / `resume` | 导航 | `{}` | 结束 / 暂停 / 继续 |
| `navigation.add_waypoint` / `remove_waypoint` | 导航 | `name` | 途经增删；追加时不得丢终点 |
| `navigation.set_preference` | 导航 | `value` | 最快 / 最短 / 避高速 / 避拥堵等 |
| `navigation.navigate_home` / `navigate_company` | 导航 | `{}` | 收藏开航；句中含途经信号时禁止抢跑 |
| `navigation.set_home` / `set_company` | 导航 | `place` | 设置家 / 公司收藏 |
| `navigation.query_eta` / `query_status` / `query_waypoints` | 导航 | `{}` | ETA / 状态 / 途经列表查询 |
| `navigation.set_prompt_enabled` | 导航 | `value: boolean` | 播报开关 ≠ 用户已听到 |
| `navigation.set_volume` / `navigation.set_muted` | 导航 | `value` | 音量 / 静音（播报诊断） |
| `life.search_shops` | 生活服务 | `keyword` | 搜店 stub；进入外卖会话 |
| `life.enter_shop` | 生活服务 | `shop_name` | 进店 stub |
| `life.add_to_cart` | 生活服务 | `item` | 加购 stub |
| `life.go_to_checkout` | 生活服务 | `{}` | 去结算 stub（不是导航目的地） |
| `life.close` | 生活服务 | `{}` | 关闭外卖会话 |

别名：`navigation.set_route` → `navigation.start`；`navigation.exit` / `navigation.nav_exit` → `navigation.stop`。

完整 Schema 以运行时 `GET /api/v1/capabilities` 为准。标准 Tool Calling 使用线名（`.` → `_`），例如 `climate_set_temperature`。

## 抢域约定（演示口径）

- 显式点外卖 / 美团等 → 进 `life.*`  
- 「顺路咖啡」等途经信号 → 优先 `navigation.add_waypoint`，不进生活域  
- 「去结算」→ `life.go_to_checkout`，禁止当成导航目的地  
- 明确「导航到 X」/ 收藏开航 → 打断并关闭外卖会话  

## 结果语义

| 维度 | 含义 |
| --- | --- |
| execution_status | 是否分发 / ACK / APPLIED / UNKNOWN |
| verification_status | 回读是否满足谓词 |
| attribution | THIS_ACTION / EXTERNAL / UNKNOWN |

ACK ≠ APPLIED；数值恰好相等也不等于本任务造成。Three.js 动画只绑定 Simulator Snapshot，不以 Tool ACK 触发几何变化。
