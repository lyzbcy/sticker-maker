# AI Memory · 表情包一键制作

> 给 AI 的渐进式入口。先读本页，只在任务相关时继续读专题文档。

## 一句话现状

`v0.2.0` 已完成 Mac（Apple Silicon）桌面闭环：首次配置、Codex 检测、生图管线、后处理、微信提交入口、AI Agent、本次运行内存日志、安装更新、介绍页与推广素材均已接入；发布前仍需真人完成一次微信开放平台冒烟。

## 当前交付

| 模块 | 状态 | 深入阅读 |
|---|---|---|
| 核心生图引擎 | ✅ 165 个 Python 测试通过 | [`status-A.md`](./status-A.md) |
| Mac 桌面应用 | ✅ 真实 arm64 `.app` 走查通过，14 个前端测试通过 | [`status-B.md`](./status-B.md) |
| 微信发布 | 🟡 已接入桌面，自动化已测试；真实账号提交待人工冒烟 | [`status-C.md`](./status-C.md) |
| AI Agent | ✅ 本地令牌接口、提示词、计划任务、启停已接入 | [`status-D.md`](./status-D.md) |
| 推广与介绍页 | ✅ 精选表情、三码、版本刷新与更新清单已完成 | [`status-E.md`](./status-E.md) |

完整逐条验收与已知边界见 [`mission-acceptance.md`](./mission-acceptance.md)。

## 关键入口

- 需求源头：`.openclaw/初心与使命.md`
- Python 引擎：`sticker_engine/`
- 桌面应用：`desktop/`
- 介绍页：`desktop/site/`
- 分发包：`desktop/表情包一键制作-mac-v0.2.0.zip`
- 设计：`docs/superpowers/specs/2026-07-25-使命收口-design.md`
- 实施记录：`docs/superpowers/plans/2026-07-25-使命收口.md`

## AI 阅读路由

- 改生图、概率、抠图：读 `architecture.md`、`status-A.md`。
- 改 Electron、安装、更新：读 `status-B.md`。
- 改微信开放平台自动化：读 `status-C.md`。
- 改 Agent 或定时任务：读 `status-D.md`。
- 改介绍页、二维码、精选展示：读 `status-E.md`。
- 判断是否能发布：只读 `mission-acceptance.md`。

## 当前版本纪律

- 应用、Python 包、网站清单统一为 `0.2.0`。
- 改网站或发布包时必须更新 `desktop/site/version.json`。
- 发布 ZIP 后必须重算 SHA-256 并写回该清单。
- 远端 `version.json` 是应用自动检查更新的唯一真源。
