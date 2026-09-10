# 评测

评测答案独立于 Planner，不进入模型 Prompt。用于回归智能终端 Agent 执行闭环：路由、策略、状态回读、故障、用户介入、出行导航可信执行，以及第二域 IoT 样例。

## 运行

```bash
# Fake 模式门禁（CI / 本地）
cd backend && mvn test

# 服务启动后
curl -X POST 'http://localhost:8080/api/v1/evals/run?mode=agent'
curl -X POST 'http://localhost:8080/api/v1/evals/run?mode=baseline'
curl -s 'http://localhost:8080/api/v1/evals/last'
```

报告默认写入 `backend/reports/`（已 gitignore）。

## 基线规模

- Fake 业务种子：**54** 例（`EvalCatalog`）
- 出行导航：**N01–N12**
- IoT 第二域：**I01–I02**（开灯 / 关灯）
- 门禁关注：`false_success=0`
- 注意：`mvn test` 显示的 JUnit 方法数是另一维度，勿与 54 混说

## 覆盖面

- FAST 明确指令与已满足跳过
- 复杂跨域复合任务与导航音频排查
- 出行导航可信执行（N01–N12）
- IoT 灯控第二域样例（I01–I02）
- ACK 未生效 / 响应丢失 / 延迟生效 / 读失败
- 策略拒绝与确认门禁
- 取消、改目标、澄清超时
- 记忆写入门禁 / 隐私拦截 / 冲突仲裁
- 生活服务 stub / 抢域由单测补充验证

`agent` 为状态反馈循环；`baseline` 为编译后一次性展开对照，二者报告分开。
