# 生图管线参考（S0→S3 + 门禁）

> **何时读**：改生图、codex 调用、切图、抠图、prompt 模板、IP 一致性时。

## 管线总览

```
S0 PrepStage     建目录、按概率选模式(single/duo/trio/quad)、选角色、按 base_probs 选 base
S1 GenerateStage 三模式分派 → 拼 prompt → codex 生图 → 废图质检 → IP 身份门禁
S2 PostprocessStage 内容感知切图 → codex 识图命名(meaning_map) → 条件抠图 → 240×240 最终版
S3 AssetsStage   横幅/封面/图标生成（auto/pick/custom/role 四模式）
```

关键文件：`stages/prep.py`、`stages/generate.py`、`stages/grid_cutter.py`、`stages/postprocess.py`、`providers/codex.py`、`resources/prompts/templates.py`、`resources/keywords.json`。

## 三模式（decide_mode 优先级）

1. `ref_lib_priority=true` 且参考图库够 n 张 → **ref_library**（base + n 张参考图，良品率最高）
2. `story_mode=true` → **story**（每行一个 4 格小故事；selector 缺失/池空降级 combo）
3. 兜底 → **keyword_combo**（45 个画面级情绪词随机组合，keywords.json 的 `{en, desc}` 结构）

## codex 调用铁律（providers/codex.py）

- **prompt 必须单行**：`_flatten_prompt` 会自动拍平。多行 prompt 经 Windows 的 codex.cmd（cmd.exe 包装）会破坏参数解析 → `-i` 参考图全部静默丢失 → 模型自创角色（2026-08-27 事故，会话 input_image=0）。
- **prompt 在 `-i` 之前**：clap 解析器里 `-i/--image` 是多值参数，会贪婪吞掉后面的位置参数。
- **参考图 ASCII 暂存**：`_stage_refs_ascii` 把中文路径图片复制到 `%TEMP%\sticker_refs\` 再传。
- `--skip-git-repo-check` 必须；stdin 必须 DEVNULL；600s 超时 + 已生成图收割。

## IP 身份门禁（generate.py `_generate_with_identity_gate`）

生成后用 `exec_text(IDENTITY_CHECK_PROMPT, refs=[grid]+bases)` 让模型对比成图与 base：
- YES → 放行；NO → 带 `URGENT IDENTITY CORRECTION` 前缀重试 1 次；再 NO → 本单作废（FAIL）
- 识图无明确回复 → WARN 放行（可用性优先）
- 废图质检 `_grid_sanity_ok`：>98% 像素同色（全黑/纯色）直接判废重试

## 内容感知切图（grid_cutter.py，2026-08-27）

背景（等分切割必切歪：GPT-4o 网格尺寸正确率仅 85-90%）：
1. 背景色检测（边框采样中位色，洋红/白底通吃）→ 前景 mask（颜色距离 >60）
2. 行/列投影 profile → 找空带沟 → **沟中下刀**（格子不齐自适应）
3. **连通域归属**：贴纸按质心分配格子，裁剪取联合 bbox（外扩 6px）→ 越界贴纸整块归属原格不被切半
4. 兜底链：无沟→等分；空格→格子矩形；线状/巨块杂块过滤；bbox 钳制 ±45% 格宽
5. `_ensure_size`：非正方形先补方再缩放（不拉伸变形）

参数都在 grid_cutter.py 顶部（`_BG_DIST_THRESH`/`_EMPTY_LINE_EPS`/`_MIN_BAND_PX` 等），切坏了先调这些。

## prompt 模板（templates.py）

三模板共用 `_STYLE_BLOCK`（Q 版规格 + 白描边贴纸 + 洋红底 + 禁止越线 + 无文字）。
身份前缀由 `_build_prompt_and_refs` 拼：`CRITICAL: draw ONLY the exact character(s)...`。
STORY 用 `{stories_description}`（每行起承转合），KEYWORD_COMBO 用 `{panels_description}`（编号场景列表，`_random_combo_panels` 生成，40% 概率点缀道具）。
