# 扩展指南：加一个新域 / 新能力（约 30 分钟）

本仓库的**不可变核心**是：

- **Harness**：任务状态机、路由、Policy、写后回读、取消隔离、评测  
- **Agent**：主 Agent / 执行规划 Agent / 审核 Agent（或 FAST 快路径）

业务域通过 **DomainModule + Capability + DevicePort** 接入，**不要改写主循环**。

## 1. 注册能力（DomainModule）

1. 新建 `XxxDomainModule implements DomainModule`
2. 在 `register(CapabilityRegistrar)` 里 `add(...)` / `alias(...)`
3. 把它加入 `CapabilityRegistry.defaultModules()`（或自定义 `new CapabilityRegistry(List.of(...))`）

参考：

- 内置终端能力：`TerminalDomainModule`
- 第二域样例：`IotDomainModule`（`iot.light.set_power`）

## 2. 效应与验收

- `CapabilityEffects.expected(...)`：写动作期望状态  
- `Verifier` / `TaskBinder`：把目标类型绑到 capability，并生成验收谓词  

灯控样例路径：`light_power` 目标 → `iot.light.set_power` → `light_power` 状态字段。

## 3. 意图编译（可选）

确定性演示 / Fake 路径可在 `GoalCompiler.detectIntents` 增加意图；真实模型路径靠 Tool Calling 选白名单工具即可。

## 4. DevicePort 适配

实现 `com.deviceagent.device.DevicePort`：

- 返回 `ActionRecord` / 使用 `FaultType`（**不要**依赖 `DeviceSimulator` 内部类型）  
- 读状态用 `StateSnapshot`  
- 本地可用 `DeviceSimulator`；接真机/机器人时新建 Adapter Bean 替换即可  

单测样例：`DomainModuleAndDevicePortTest.InMemoryLightPort`。

## 5. 评测

在 `EvalCatalog` 增加独立断言种子；门禁仍看 `false_success=0`。  
当前基线含终端能力 + 导航 N01–N12 + IoT I01–I02。

## 检查清单

- [ ] 未修改 `HarnessService` 主循环语义  
- [ ] 新能力出现在 `GET /api/v1/capabilities`  
- [ ] Fake / 真模型都能选到该工具（白名单）  
- [ ] 有状态回读验收，不以 ACK 当成功  
- [ ] `mvn test` 通过  
