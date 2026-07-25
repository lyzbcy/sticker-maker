# D AI Agent · 状态

> **何时读**：修改外部 Agent 接入、令牌、计划任务或桌面工具面板时。

## 已完成

- 桌面端可启动/停止本地 Agent 服务并查看状态。
- 首次启动生成令牌；受保护接口使用 Bearer token。
- `/agent-prompt` 提供可直接交给外部 Agent 的控制说明。
- 支持立即运行、发布、批量发布、上架，以及 APScheduler 定时动作。
- 调度状态保存在用户数据目录；日志仍遵循近 50 条内存策略。

## 关键文件

- `sticker_engine/sticker_engine/agent/server.py`
- `sticker_engine/sticker_engine/agent/scheduler.py`
- `sticker_engine/sticker_engine/agent/AGENT_PROMPT.md`
- `desktop/src/renderer/components/ToolsPanel.vue`

## 安全边界

- 默认只监听 loopback，不直接暴露公网。
- 令牌不进入运行日志。
- 外部 Agent 不应绕过软件的概率校验、发布前检查或平台登录要求。
