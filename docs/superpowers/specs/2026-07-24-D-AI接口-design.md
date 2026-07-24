# D. AI Agent 接口 — 设计文档（Spec）

> **子项目**：D（5 个子项目中的第四个）
> **状态**：待用户审阅
> **依赖**：A 核心（CLI JSON-lines）+ C 发布（定时发布用例）

---

## 0. 职责

给外部 AI agent 一个**控制软件的 HTTP 接口**，让 agent 能：一键走完全流程（生图→发布）、定时发布、查询状态等。配套一份 agent prompt，用户复制即可把自己的 AI agent 接入。

来源：初心第 70-71 行"提供 ai 接口，给出 prompt，让用户接入 ai-agent 控制软件"。

## 1. 关键决策

| # | 决策 | 选择 | 理由 |
|---|---|---|---|
| D1 | 接口形态 | **本地 HTTP 服务**（包装 A 的 CLI） | agent 都会 HTTP；复用 CLI 全部命令；不重写业务 |
| D2 | 长任务（run） | **SSE 推送进度** | run 是分钟级，HTTP 请求不能阻塞；SSE 流式推 progress 事件 |
| D3 | 定时发布 | **内置 scheduler**（cron 风格） | 初心第 71 行明确用例；agent 调 "schedule" 接口注册 |
| D4 | agent prompt | **独立 md 文档 + 内置 /agent-prompt 端点** | 用户可复制；也能 HTTP 拉取 |
| D5 | 认证 | **本地 loopback + token** | 防止局域网误调用；token 首次启动生成 |

## 2. 架构

```
外部 AI agent
   ↓ HTTP（localhost:7432）
┌──────────────────────────────────────┐
│  D: agent_server.py（FastAPI/Flask） │
│  - POST /run          → 生图（SSE）   │
│  - POST /publish      → 发布一弹       │
│  - POST /batch        → 批量发布       │
│  - POST /shelf        → 上架           │
│  - GET  /status       → 状态查询       │
│  - POST /schedule     → 注册定时任务   │
│  - GET  /agent-prompt → 拉 agent 提示词│
└──────────────┬───────────────────────┘
               │ 复用（不重写）
┌──────────────▼ A 的 CLI + C 的 publish-cli ──┐
│  sticker_engine.cli（JSON-lines）            │
│  sticker_engine.publish.cli（发布）           │
└──────────────────────────────────────────────┘
```

**核心原则**：D 是薄 HTTP 层，**不重写任何业务逻辑**——所有动作转发到 A 的 CLI 或 C 的 publish-cli。对应初心第 73 行"复用脚本写死，节约 token"。

## 3. API 设计

| 方法 | 路径 | 作用 | 返回 |
|---|---|---|---|
| GET | `/status` | 查 codex/prefs/历史 | JSON |
| POST | `/run` | 生图（SSE 流式进度） | text/event-stream |
| POST | `/stop` | 取消当前 run | JSON |
| POST | `/publish` | 发布指定 episode | JSON |
| POST | `/batch` | 批量发布 | JSON（后台任务 id） |
| POST | `/shelf` | 自动上架 | JSON |
| POST | `/schedule` | 注册定时任务（cron） | JSON（job id） |
| GET | `/schedules` | 列定时任务 | JSON |
| DELETE | `/schedule/{id}` | 删定时任务 | JSON |
| GET | `/agent-prompt` | 拉 agent 接入提示词 | text/plain |

请求头：`Authorization: Bearer <token>`（loopback 也带，防误调）。

## 4. agent prompt（初心第 71 行"给出 prompt"）

独立文档 `sticker_engine/agent/AGENT_PROMPT.md`，内容示例：

```markdown
# 你的 AI agent 可以控制「表情包一键制作」

本机有一个 HTTP 服务（localhost:7432）控制表情包制作软件。
你可以调用以下接口：

## 快速开始
1. 先 GET /status 看状态（codex 是否就绪）
2. POST /run 生图（返回 SSE 流，读到 percent=1.0 完成）
3. POST /publish {episode_dir} 发布

## 定时发布
POST /schedule {cron: "0 9 * * *", action: "run"}  # 每天9点生图

## 示例对话
用户："帮我生成一组表情并发到微信"
你：1. POST /run → 等完成 → 2. POST /publish
```

也通过 `/agent-prompt` 端点拉取（agent 可自动获取）。

## 5. 定时发布（scheduler）

用 `apscheduler`（轻量）：
- `POST /schedule` 注册：`{cron, action, args}` → 返回 job_id
- action: "run" / "publish" / "batch" / "shelf"
- 持久化到 `~/Library/Application Support/StickerEngine/schedules.json`
- 服务重启后自动恢复

## 6. 目录结构

```
sticker_engine/agent/               ← D 新建
├── __init__.py
├── server.py                       ← HTTP 服务（Flask，stdlib 无重依赖）
├── scheduler.py                    ← 定时任务（apscheduler）
├── AGENT_PROMPT.md                 ← agent 接入提示词
└── cli.py                          ← agent-server 启动入口
```

**技术选型**：用 **Flask**（轻量，依赖少）。FastAPI 也行但 FastAPI + uvicorn 依赖更重。Flask + 自带 server 够用（loopback 单用户场景）。SSE 用 Flask 的 generator response。

## 7. 测试

- server.py 各端点（mock 转发层，断言调用了正确的 CLI/publish 命令）
- scheduler 注册/列出/删除/持久化
- token 认证（无 token 拒绝）
- SSE run（mock run 流，断言事件序列）

## 8. 验收

1. ✅ `agent-server` 启动，监听 localhost:7432
2. ✅ GET /status 返回 codex/prefs 状态
3. ✅ POST /run 返回 SSE 流（progress → result）
4. ✅ POST /publish 转发到 publish-cli
5. ✅ 定时任务注册/列出/删除/持久化
6. ✅ 无 token 请求被拒（401）
7. ✅ GET /agent-prompt 返回提示词
8. ⏳ 真实 agent 接入（你回来用真实 agent 测）

## 9. 下一步

spec 审阅 → 实现。
