# A 核心生图引擎 · 完成度与技术债

> **何时读**：要看 A 到底做到哪了、有哪些坑没填。

## 完成度：可交付（含 1 项需真实环境验证）

- 源码 ~1700 行 / 25 文件，测试 ~900 行 / 16 文件，**77 测试全绿**
- 抠图 A/B 验收红线达标：5/5 真实素材差异 < 10%
- 决策 K（AI 走 codex）已落地：含义预检 + 介绍文案真实调 codex.exec_text

## 已修复的 Critical（不再列）

C1（mode 流转）/ C2（失败语义）/ I6+M3（base 概率 + prefs）—— 见 commit `fix(A): 评审 Critical 修复`。

## 已补完的核心项（本轮）

- ✅ **I5** CodexProvider.exec_text() 捕获 codex 文本输出
- ✅ **I2** VisionProvider 真实调 codex 做含义预检 + 介绍文案（解析纯 JSON + ```json 围栏，失败降级 含义N）
- ✅ 参考图库自动创建（初心第 31 行）
- ✅ ai-memory doc 目录（初心第 96 行，本目录）

## 遗留技术债（按优先级）

### 需真实 codex 环境验证（B 子项目跑起来后）

| # | 问题 | 说明 |
|---|---|---|
| I1 | `stop_event` 在 codex 生图期间无法中断 | codex 调用是阻塞的（最长5分钟），改 `Popen` + 轮询可修。B 接取消按钮前修 |
| I2验证 | 含义预检/介绍文案的真实 codex 输出 | 代码已写真实逻辑（mock 测过），但没真实 codex 跑过。B 能跑 codex 时端到端验证 |

### 打包相关（B 必须修）

| # | 问题 | 说明 |
|---|---|---|
| C3 | `pyproject.toml` 的 `base_images/*` glob 不递归 | wheel/sdist 不含 base 图（开发模式能跑）。改 `base_images/*/*` 或 `include_package_data` |

### 质量增强（后续迭代）

| # | 问题 | 说明 |
|---|---|---|
| I3 | production_log 只有 4 条 stage 级，非 spec 的 7 必经步骤 | Gate PASS 也应记日志；S2 拆子步骤 |
| I4 | Gate1/Gate2 检查项偏简 | Gate1 应查非空/尺寸；Gate2 应查数量==grid² |
| M1 | ModeProbs 三份并行数据类 | 改一处易漏，应单一真源 |
| M2 | PipelineRunner step 归一化过度灵活 | YAGNI，可收敛 |
| M5 | config/loader.py 缺三层合并入口 | api.py 里 reimplement 了 yaml 读取 |
| M6 | AssetsStage._pick_best_face 取第1张 | 应移植 face_detect |
| M7 | A/B 测试用 remove_key 非 remove_key_auto | 绿色回退分支未做像素对齐 |

## 测试矩阵

- 单元：providers（codex/chromakey/vision）、stages（prep/generate/postprocess/assets）、story、config、pipeline
- 集成：6 个（成功路径/参考图库不抠/base 概率/codex失败/stop事件/进度序列）
- A/B：5 个真实素材抠图对齐
- chromakey 自证：5000 像素向量化 vs colorsys 基准对齐
