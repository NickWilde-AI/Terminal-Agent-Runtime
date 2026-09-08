# 评测

评测答案独立于 Planner，不进入模型 Prompt。用于回归智能终端 Agent 执行闭环：路由、策略、状态回读、故障与用户介入。

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

## 覆盖面

- FAST 明确指令与已满足跳过
- 复杂跨域复合任务与导航音频排查
- ACK 未生效 / 响应丢失 / 延迟生效 / 读失败
- 策略拒绝与确认门禁
- 取消、改目标、澄清超时
- 记忆写入门禁 / 隐私拦截 / 冲突仲裁

`agent` 为状态反馈循环；`baseline` 为编译后一次性展开对照，二者报告分开。
