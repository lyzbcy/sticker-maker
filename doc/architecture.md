# A 核心生图引擎 · 架构

> **何时读**：要改 A 的代码、或理解 A 怎么被 B/C/D 调用。

## 分层（依赖单向向下）

```
上层(B GUI / C 发布 / D agent) ──→ api.py  StickerEngine.run()
                                          │
                                   pipeline/runner.py  (顺序跑 Stage + Gate 关卡)
                                          │ 传递 PipelineContext
              ┌──────────┬────────────────┼───────────┬───────────┐
              ▼          ▼                ▼           ▼           ▼
         stages/prep  stages/generate  stages/postprocess  stages/assets
              │          │                │           │
              │     ┌────┴────┐      ┌────┴────┐      │
              ▼     ▼         ▼      ▼         ▼      ▼
          providers/codex  providers/chromakey  providers/vision
              │          （内置抠图）        （含义/文案，走 codex）
              ▼
          resources/（只读内置资产：4角色base图、174剧本、关键词库）
```

## 四 Stage + 三 Gate

| 阶段 | 作用 | Gate |
|---|---|---|
| S0 Prep | 建目录、选模式/角色/base（按概率）、写角色卡、**自动建参考图库** | → Gate0（codex 可用） |
| S1 Generate | 三模式分派（参考图库/故事/排列组合）→ 调 codex → 捞图 | → Gate1（grid 图存在） |
| S2 Postprocess | 裁切 → 含义预检（codex 识图）→ 条件抠图 → 重命名 | → Gate2（数量/含义词） |
| S3 Assets | 横幅 750×400 / 封面 240×240 / 图标 50×50 / 介绍.txt | |

## 关键契约（B/C/D 调 A 靠这些）

**入口**：
```python
engine = StickerEngine(config)
episode = engine.run(progress_callback=cb, stop_event=event)
```

**产出 `Episode`**：
- `success: bool` — False 表示关卡 FAIL 或异常，调用方必须检查
- `errors: list[GateError]` — 关卡失败原因
- `episode_dir / stickers / meaning_map / assets / production_log`

**进度回调 `ProgressEvent`**：`(stage, phase, message, percent, eta_seconds)`

**停止**：`stop_event.set()` —— 注意当前只在 stage 之间生效，codex 生图期间（最长5分钟）无法中断（已知技术债 I1）。

## 抠图条件矩阵（spec 3.3，核心纪律）

| 生图模式 | 默认背景 | 默认是否抠图 |
|---|---|---|
| 参考图库模式 | 保留参考图背景 | 否（除非 transparent=True） |
| prompt 模式（故事/排列组合） | 洋红 #ff00ff | 是 |
| 1×1 生图 | — | 不切图 |

S1 把决出的 `gen_mode` 写进 `ctx.gen_mode`，S2 据此决定抠不抠。

## 依赖外部

- **codex CLI**（用户自备，决策 A1）：生图 + 含义预检 + 介绍文案（决策 K）
- 抠图是**内置**的（Pillow+numpy hue-guard），不依赖 codex

## 详细 spec

完整设计见 `docs/superpowers/specs/2026-07-24-A-核心生图引擎-design.md`。
