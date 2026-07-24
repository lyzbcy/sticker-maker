# AI Memory · 表情包一键制作

> **这个目录是给 AI 看的**（初心与使命第 96 行）。
> 目标：让任何 AI 用最小上下文理解项目现状，按需深入。

## 怎么用这个目录（渐进式披露）

**只读这一篇 README，就能知道项目是什么、做到哪了、下一步干嘛。**
需要细节时，再点进对应专题文档——每个专题文档开头都标了"何时读它"。

不要一上来全读。按需展开。

---

## 项目一句话

把"微信表情包制作+发布"流程打包成 Mac 桌面软件（对外品牌名"表情包一键制作"），分发给粉丝使用。核心生图依赖 codex CLI（用户自备）。

## 当前进度（2026-07-24）

| 子项目 | 状态 | 说明 |
|---|---|---|
| **A. 核心生图引擎** | ✅ 交付 | Python 库 `sticker_engine/`，77 测试全绿 |
| B. Mac 应用外壳 | ⏳ 未开始 | GUI、首次向导、`.app` 打包 |
| C. 发布与上架 | ⏳ 未开始 | 跨平台发布流、一键多平台 |
| D. AI Agent 接口 | ⏳ 未开始 | 外部 agent 控制、定时发布 |
| E. 推广系统 | ⏳ 未开始 | 表情包推广、三码 |

**当前可做**：A 已可作为地基，启动 B 的 brainstorm。

## 专题文档（按需读）

| 文档 | 何时读 |
|---|---|
| [`./architecture.md`](./architecture.md) | 要改 A 的代码、或理解 A 怎么接 B/C/D |
| [`./decisions.md`](./decisions.md) | 要知道某个设计为什么这么定（13 个关键决策） |
| [`./status-A.md`](./status-A.md) | 要看 A 的完成度细节、已知技术债 |
| [`./how-to-run.md`](./how-to-run.md) | 要跑/测 A |

## 关键文件指针

- 需求源头：`.openclaw/初心与使命.md`
- A 的 spec：`docs/superpowers/specs/2026-07-24-A-核心生图引擎-design.md`
- A 的实现计划：`docs/superpowers/plans/2026-07-24-A-核心生图引擎.md`
- A 的代码：`sticker_engine/`
- git 分支：`feature/A-core-engine`
