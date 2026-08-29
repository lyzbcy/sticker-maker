# AI Memory · 表情包一键制作

> 给 AI 的渐进式入口。先读本页，只在任务相关时继续读专题文档。
> 项目开发 skill：`.agents/skills/sticker-maker-dev/SKILL.md`（开发纪律 + 已知坑速查）。

## 一句话现状

`v0.3.0` 双平台（Windows + Mac）闭环：向导配置 → codex 三模式生图（含 **IP 身份门禁**）→ **内容感知切图**（投影找沟 + 连通域归属，不再被格线切歪）→ 系列自动命名（「周三涵做表情 N」）→ 账号密码自动登录发布到微信平台（keyring 存凭据）。已真实发布过专辑。后端 200 测试 / 前端 32 测试全绿。

## 当前交付

| 模块 | 状态 | 深入阅读 |
|---|---|---|
| 核心生图引擎 | ✅ 200 个 Python 测试通过 | [`status-A.md`](./status-A.md) + [`reference/pipeline.md`](./reference/pipeline.md) |
| 桌面应用（Win+Mac） | ✅ 真实走查通过，32 个前端测试 | [`status-B.md`](./status-B.md) |
| 微信发布 | ✅ 密码自动登录 + 全字段自动填写 + 真实提交成功 | [`status-C.md`](./status-C.md) + [`reference/publish.md`](./reference/publish.md) |
| 系列/作品库 | ✅ 系列编号 + 全部作品 + 详情页 | [`reference/series.md`](./reference/series.md) |
| 平台审核驳回 | 🔧 驳回理由抓取/展示/一键评审 + 整改记录 | [`reference/platform-review.md`](./reference/platform-review.md) |
| AI Agent | ✅ 本地令牌接口、提示词、计划任务、启停已接入 | [`status-D.md`](./status-D.md) |
| 推广与介绍页 | ✅ 精选表情、三码、版本刷新与更新清单 | [`status-E.md`](./status-E.md) |

完整逐条验收与已知边界见 [`mission-acceptance.md`](./mission-acceptance.md)。

## 关键入口

- 需求源头：`.openclaw/初心与使命.md`
- Python 引擎：`sticker_engine/`
- 桌面应用：`desktop/`
- 介绍页：`desktop/site/`
- 设计：`docs/superpowers/specs/2026-07-25-使命收口-design.md`
- 实施记录：`docs/superpowers/plans/2026-07-25-使命收口.md`

## AI 阅读路由

- 改生图、概率、抠图、**切图**：读 `architecture.md`、`status-A.md`、`reference/pipeline.md`。
- 改 Electron、安装、更新：读 `status-B.md`。
- 改微信开放平台自动化：读 `status-C.md`、`reference/publish.md`。
- 改系列命名、作品库、详情页：读 `reference/series.md`。
- 改 Agent 或定时任务：读 `status-D.md`。
- 改介绍页、二维码、精选展示：读 `status-E.md`。
- 判断是否能发布：只读 `mission-acceptance.md`。

## 当前版本纪律

- 应用、Python 包、网站清单统一为 `0.3.0`。
- 改网站或发布包时必须更新 `desktop/site/version.json`。
- 发布 ZIP 后必须重算 SHA-256 并写回该清单。
- 远端 `version.json` 是应用自动检查更新的唯一真源。
