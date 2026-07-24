# Prompt Templates

## ⚠️ 角色防侵权铁律（最高优先级）

**CODE. RED. 违反此项将导致侵权风险，严禁跳过。**

```
-i 参数的顺序决定生命：
  -i 第1个 = base角色图（主角，必须用此角色）
  -i 第2-5个 = 参考图（仅借pose/composition，禁止用其角色）

❌ 禁止：只传 -i 参考图而不传 base图
❌ 禁止：base图放第2个或更后面
❌ 禁止：prompt 中不强调"use image 1 character only"
✅ 必须：每句 prompt 开头注明 "Image 1 is the ONLY character to use"
✅ 必须：生图后做角色身份核对（codex 视觉检查主角是否=base图角色）
```

**Codex 命令格式（不可变）：**
```powershell
codex exec --enable image_generation --skip-git-repo-check -i "BASE角色图.png" -i "参考图1.png" -i "参考图2.png" -i "参考图3.png" -i "参考图4.png"
#                                    ^^^ IMAGE 1 = 主角      ^^^ IMAGE 2-5 = 仅借pose
```

## 使用原则

1. PowerShell 下尽量用英文 prompt。
2. prompt 通过 stdin pipe 传给 codex。
3. 不要依赖 `transparent background`。
4. 视觉复核含义词时，以图像真实内容为准。
5. **生图后必须做角色身份核对**（见底部「角色身份核对 Prompt」）。
6. **🔴 禁止生成投影阴影**：洋红 Chroma-key 背景下，角色投射的阴影（drop/contact/ground shadow）会与背景色重叠，抠图时剔除不干净，残留粉边。立体感必须来自材质本身的明暗渐变（subsurface scattering），不靠投影。所有 prompt 的 `<style>` 已改为 flat front lighting，严禁再写 "soft realistic shadows" 之类正向阴影词。

## 四宫格参考图模式

```text
Generate a 4-panel plush doll style image.

For each panel, use the reference image as template for POSE AND COMPOSITION ONLY. The expression/action this panel should convey is noted below, COMPLETELY replace ALL characters with the character from image 1:
- Top-left: Use image 2 (expression: {ref2_name}), COMPLETELY replace characters with image 1, keep the pose.
- Top-right: Use image 3 (expression: {ref3_name}), COMPLETELY replace characters with image 1, keep the pose.
- Bottom-left: Use image 4 (expression: {ref4_name}), COMPLETELY replace characters with image 1, keep the pose.
- Bottom-right: Use image 5 (expression: {ref5_name}), COMPLETELY replace characters with image 1, keep the pose.

CRITICAL RULES:
- DO NOT include ANY original characters from reference images. Only the character from image 1 must appear.
- The character MUST be cute, adorable, well-proportioned.
- Maintain kawaii/chibi aesthetic.

BACKGROUND (mandatory): Perfectly flat solid #ff00ff chroma-key magenta background (RGB 255,0,255), filling the entire image with no shadows, gradients, or texture. Do NOT use #ff00ff anywhere on the character.
The character must NOT cast any shadow (drop/contact/ground shadow) onto the magenta background — use flat front lighting; volume comes from material shading, not projected shadows.
Style: Plush doll / soft toy texture (soft fuzzy fabric surface, gentle stuffing volume, subtle seam stitching, matte felt-like material), cute chibi expressions, soft warm colors.
IMPORTANT: All 4 panels must be exactly the same size, evenly distributed, no gaps, no grid lines.
```

## 四宫格 AI 模板模式

```text
Create a 4-panel cute sticker image.
Character: Use image 1 as reference. Chibi style (large head, small body, 1:1.2 ratio).
Style: Plush doll / soft toy texture (soft fuzzy fabric surface, gentle stuffing volume, subtle seam stitching, matte felt-like material), soft warm colors, simple but effective shading.
Expression guidelines:
- Each panel should clearly convey one specific emotion
- Exaggerated but cute poses and facial expressions
- Include body language
- Add slight blush on cheeks for cuteness
BACKGROUND (mandatory): Perfectly flat solid #ff00ff chroma-key magenta background (RGB 255,0,255), filling the entire image with no shadows, gradients, or texture. Do NOT use #ff00ff anywhere on the character.
The character must NOT cast any shadow (drop/contact/ground shadow) onto the magenta background — use flat front lighting; volume comes from material shading, not projected shadows.
Composition: Character centered with proper whitespace, balanced layout.
Panel emotions:
Top-left: {emotion_1}
Top-right: {emotion_2}
Bottom-left: {emotion_3}
Bottom-right: {emotion_4}
```

## 双人模式 Prompt

```text
Create a 4-panel cute sticker image featuring TWO characters.
Character A: Use image 1 as reference.
Character B: Use image 2 as reference.
Style: Plush doll / soft toy texture, soft warm colors.
Expression guidelines:
- Both characters should interact with each other
- Exaggerated but cute poses and facial expressions
- Show their relationship through body language
BACKGROUND (mandatory): Perfectly flat solid #ff00ff chroma-key magenta background (RGB 255,0,255), filling the entire image with no shadows, gradients, or texture. Do NOT use #ff00ff anywhere on the characters.
The characters must NOT cast any shadow (drop/contact/ground shadow) onto the magenta background — use flat front lighting; volume comes from material shading, not projected shadows.
Panel emotions:
Top-left: {emotion_1}
Top-right: {emotion_2}
Bottom-left: {emotion_3}
Bottom-right: {emotion_4}
```

## 四人模式 Prompt

```text
Create a 4-panel cute sticker image featuring FOUR characters.
Character A: Use image 1 as reference.
Character B: Use image 2 as reference.
Character C: Use image 3 as reference.
Character D: Use image 4 as reference.
Style: Plush doll / soft toy texture, soft warm colors.
BACKGROUND (mandatory): Perfectly flat solid #ff00ff chroma-key magenta background (RGB 255,0,255), filling the entire image with no shadows, gradients, or texture. Do NOT use #ff00ff anywhere on the characters.
The characters must NOT cast any shadow (drop/contact/ground shadow) onto the magenta background — use flat front lighting; volume comes from material shading, not projected shadows.
Panel emotions:
Top-left: {emotion_1}
Top-right: {emotion_2}
Bottom-left: {emotion_3}
Bottom-right: {emotion_4}
```

## 九宫格帧图 Prompt

```text
Plush doll style, 3x3 grid layout, no gaps, no grid lines, no numbers.
Each cell is exactly the same size.
All cells show the same character (from image 1).
From left to right, top to bottom: animation frames 1 to 9, smooth transitions between frames.
Center composition, proper margins around the character.
BACKGROUND (mandatory): Perfectly flat solid #ff00ff chroma-key magenta background (RGB 255,0,255), filling the entire image with no shadows, gradients, or texture. Do NOT use #ff00ff anywhere on the character.
The character must NOT cast any shadow (drop/contact/ground shadow) onto the magenta background — use flat front lighting; volume comes from material shading, not projected shadows.
Keep the original background only if it is already pure #ff00ff magenta.
```

## 角色身份核对 Prompt ⚠️ 防侵权必做

生图后立即对每组四宫格做角色身份核对。如有任一格用了参考图角色，整组废弃重做。

```text
Compare this generated 4-panel image with the BASE character image.
Look at EVERY panel carefully.
Question: Does EVERY panel show ONLY the character from the BASE image?
If YES: reply "PASS: 主角正确，全部4格均为base角色"
If NO: reply "FAIL: 第X格出现了参考图角色（描述具体哪里不对），需要重做"
```

## 视觉复核含义词 Prompt

```text
Output one line per image: 'IMAGE_N: MEANING'
where MEANING is the best 2-4 Chinese chars describing
what the chibi character(s) are doing.
```

## 背景与透明策略

### 🔴 禁止生成投影阴影（抠图质量第一防线）

**这是洋红 Chroma-key 抠图最关键的一条规则，比任何抠图参数都重要。**

原因链：
1. 角色被要求投阴影时，模型会把洋红背景色「调暗」画成投影（典型 RGB≈216,22,203）。
2. 这些阴影像素介于「纯洋红」和「角色色」之间，是洋红的暗调变体。
3. 抠图脚本靠「与洋红的距离」判断透明度，阴影像素距离不够大 → 被判定为半透明 → 残留粉边/灰边。

**结论：从生图端不画投影，是最干净的治本方案。** 立体感由 3D clay 材质本身的明暗渐变（subsurface scattering）提供，不需要投影。

生图端已落实（见各模板的 `LIGHTING` / `BACKGROUND` / checklist 行）：
- `<style>` 段：`flat even front lighting`，严禁 `soft realistic shadows`
- `BACKGROUND` 行：明确 `NO drop/contact/ground/cast shadow`
- checklist：生图前自检无阴影

> 注意：抠图端的 `chroma_key.transparent_threshold=150` 是为了兜底**历史已生成的**带阴影图（19/20 弹及更早）。新弹次从源头禁阴影后，阴影残留问题将不再产生。

### 🔴 洋红色值定义（生图端与抠图端必须严格一致）

这是整个透明流程最关键的对齐点。**生图 prompt 里写的洋红** 和 **抠图脚本去掉的洋红** 必须是同一个色值，否则会残留洋红边、漏抠或误抠角色。

```
统一色值：#ff00ff = RGB(255, 0, 255)
  - 生图端：写在每个 prompt 的 BACKGROUND 行（见上方各模板）
  - 抠图端：main.py process_chroma_key() 调用 remove_chroma_key.py 时
            用 --key-color #ff00ff 显式传入，不要用 --auto-key
  - 兜底色：#00ff00 = RGB(0, 255, 0)（仅当角色本身偏洋红/偏粉时才改用）
```

> ⚠️ `remove_chroma_key.py` 自身 `--key-color` 默认是 `#00ff00`（绿色），不是洋红！
> 如果不显式传 `--key-color #ff00ff`，又用了 `--auto-key none`，就会按绿色去抠，
> 而图里根本是洋红 —— 这就是历史上抠图质量差的原因之一。

> ⚠️ **不要加 `--despill`！** 洋红的 spill 清理（`_cleanup_spill`）会把边缘洋红
> 像素的 R/B 通道压到等于 G 通道，结果边缘半透明像素变成灰色，贴白底显示为
> 灰色光晕。
>
> ⚠️ **必须加 `--transparent-threshold 80`！** 生成图背景不是纯 #ff00ff，有渐变/
> 噪点（角落常是 250,0,233 之类）。仅 `--soft-matte` 默认阈值会让背景像素只变
> 半透明(alpha 10~73)而非全透明，成品显示成粉红底。加阈值后背景全透明。
>
> ⚠️ **必须加 `--edge-contract 1`！** 角色边缘有洋红混色过渡像素（洋红背景+角色
> 色的混合），仅 alpha 羽化会让它们半透明但 RGB 仍是洋红，贴白底显示成粉红边。
> edge-contract 收缩 alpha 蒙版 1px 把洋红混色吃进透明区，留下干净角色色。
> 实测：洋红边缘像素 460→43 (减91%)，且不染灰（区别于 despill）。
>
> 正确调用：
> ```
> remove_chroma_key.py --input X --out Y --key-color #ff00ff --auto-key none \
>   --soft-matte --transparent-threshold 80 --edge-contract 1
> ```

### 不透明背景保留模式

- 有参考图时通常不指定背景
- 适合保留参考图原生氛围

### 纯透明模式（默认）

- 生成时 prompt 里写死纯色 `#ff00ff` Chroma-key 背景（已烘焙进 config.yaml 模板）
- 再本地用 remove_chroma_key.py 按 `#ff00ff` 去背景
- 抠图调用示例见 `main.py process_chroma_key()`

### 颜色选择经验

- **默认：洋红 `#ff00ff`（RGB 255,0,255）**（大多数角色适用）
- 极少数偏洋红/偏粉角色：改用绿色 `#00ff00`（需同时改生图 prompt 和抠图 --key-color，两端保持一致）

## Codex CLI 提醒

正确示例：

```powershell
$prompt | codex exec --enable image_generation -i "base.png"
```

避免：

- 把 prompt 当命令行参数直传
- 用中文 prompt 通过 PowerShell pipe
- 再加 `transparent background`（现在用 `#ff00ff` 实色背景 + 本地抠图）

