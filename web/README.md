# Web 工作台

智能终端 Agent Runtime 联调界面（React + TypeScript + Vite），由 nginx / Vite 代理到后端 `/api`。

```bash
# 仓库根目录
./scripts/run_web.sh
```

生产构建由 `./scripts/start.sh` 触发，静态资源打入 `web` 镜像。
