---
name: lyzbcy-sticker-creator
description: "微信表情包创作系统。以分阶段工作流驱动生图、裁剪、透明处理、重命名和发布素材生成,优先保证稳定产出而非一键全自动。"
---

中文名称:微信表情包自动化创作系统
能力简介:分阶段、可校验、可回退的表情包创作系统,目标是让不同 AI 都能稳定完成创作链路。
使用场景:批量生成微信表情包,支持静态和动态表情,优先适配多模型、多 agent 执行。
参数提示:[prep|generate|postprocess|assets|publish] <参数>

# 微信表情包自动化创作系统 - Sticker Creator

## AI 统一执行协议

<system-goal>
本 skill 的目标不是"看起来全自动",而是"让不同 AI 按同一流程稳定产出"。
优先走分阶段工作流:准备 -> 生图 -> 校验 -> 后处理 -> 校验 -> 发布素材 -> 最终校验 -> 发布。
如果某一步不确定,宁可停在当前关卡报错,也不要跳步或脑补成功。
</system-goal>

<creator-hard-rules>
1. 先读 `E:\星星布丁\微信表情包\.openclaw\skills\README.md` 的总规范，再执行本 skill。
2. 优先使用 `prep_episode.py` 和 `validate.py`，不要一开始就把 `main.py` 当成唯一入口。
3. 不要把"参考图文件名"直接当成最终含义词，发布前必须做视觉复核。
4. **生图背景策略**：默认使用纯洋红 #ff00ff Chroma-key 背景，随后用本地脚本抠图。仅当角色本身偏洋红/偏粉时才改用绿色 #00ff00（需提前确认角色肤色）。
   - **🔴 红衣/粉衣 chroma-key 保护**：角色穿红色/粉红色衣服时（如"衣服染色"故事），洋红 key 会把红衣误抠成破洞（同类色在 RGB 重叠）。`remove_chroma_key.py` 已内置 hue-guard（HSV 双判据，默认开启）保护这类前景。若遇到角色被抠空，先用 `python rechroma_test.py --hue-guard --image <图>` 诊断"红衣误伤率"。详见 troubleshooting 第7坑，不要手调 `transparent_threshold` 凑数。
5. 对用户汇报时，要区分"脚本已自动完成"与"仍需人工或视觉复核"。
6. **严禁造假凑数**：如果遇到生图失败或图片不够，严禁通过复制和重命名旧图片来凑足 16 张！重复表情一定会被微信平台审核打回，必须重试生图。
7. **🔴 默认 4×4 生图**：生成表情包统一使用 4×4 十六宫格（配置项 `generation.default_grid: 4`）。16 张数量刚好满足微信 12-24 要求，且 3D clay 风格下 4×4 效果优于 3×3。仅在用户明确指定其他宫格时才调整。
8. **🔴 角色防侵权（最高优先级）**：`codex exec` 的 `-i` 参数第一个必须是 base 角色图（主角），后续才是参考图（仅借 pose）。生图后必须对每组四宫格做角色身份核对（见 `reference/prompt-templates.md`）。如果任一格用了参考图角色而非 base 角色，该组必须废弃重做。**严禁在未传 base 图的情况下用参考图生成表情包**——这可能导致发布他人原创角色造成侵权。
9. **AI 文案与可爱度参与**：AI 不只执行脚本，还要参与表情介绍和提示词审美。每弹发布前写 `介绍.txt`（1-80 字，描述特点和故事）；使用 AI 模板提示词生图前，先审一遍提示词是否软萌、清楚、有聊天场景，偏冷/暴力/生硬的词必须改成可爱表达。
10. **🔴 联动剧本优先 + 多故事串联（最高创作优先级）**：表情包不是16个独立情绪，而是16个能"对话"的角色。生图前**必须先设计联动剧本**，从 `linkage_scripts.json` 抽取 **4 组剧本**（每组4 panel，共16 panel），**4×4十六宫格的每一行是一个独立小故事**（4格讲一个起承转合），4行=4个不同故事串联。这样每格都有独立笑点，题材多元。**严禁退回随机情绪组合模式**，除非 `linkage_scripts.json` 不可用。**严禁把单个故事硬撑成16格**（详见设计系统说明）。
</creator-hard-rules>

<linkage-design-system>
### 联动剧本设计系统（核心创作方法论）

**核心理念**：好的表情包不是16张独立情绪图，而是16个能"对话"的角色。用户在聊天中前后发送两张表情，会在上下窗口产生意想不到的互动效果——这是表情包的"灵魂"。

**联动类型（4种）：**

| 类型 | 说明 | 示例 |
|------|------|------|
| **动作衔接** | Panel A 做动作，Panel B 是反应 | A伸手要抱抱 → B一巴掌拍开 |
| **剧情连续** | 完整的微故事线 | 饿了→大口吃→吃撑了→满足 |
| **反转** | 前半铺垫，后半反转 | 自信登场→嘚瑟→滑倒→摔了 |
| **对话** | 像两个角色在互动 | A:看热闹 → B:喝茶 → A:偷笑 |

**生图流程：**

```
参考图 ≥ 16 张 → 参考图模式（base图 + 16张参考图，天然不重复）
参考图 < 16 张 → 联动剧本模式（base图 + 4组小故事，每行1个故事=4格，共16格）
```

两种模式都带 base 图（遵守铁律8：防侵权）。参考图优先，不够时自动回退联动剧本。

**角色驱动的剧本选取（多故事串联架构）：**
1. `prep_episode.py` 先决定模式（单人/双人/四人）和角色
2. `generate_from_prep_state.py` 根据角色从 `linkage_scripts.json` 筛选匹配剧本
3. **一弹选 4 组剧本**，每组 4 个 panel —— **16宫格的每一行 = 一个独立小故事**（第1行=故事A的1-4格，第2行=故事B的5-8格，第3行=故事C的9-12格，第4行=故事D的13-16格）
4. 没标 `characters` 的剧本 = 通配，任何角色可用
5. **用过的剧本永久淘汰**（`used_linkages.txt` 记录），不再循环使用

**剧本结构要求（标准4格）：**
- 每组剧本 **标准就是 4 个 panel**（起承转合）：起（铺垫）→ 承（发展）→ 转（转折/高潮）→ 合（结局）
- 4 格讲完一个完整小故事，每格都有独立笑点，单发也能看懂
- 示例（4格）：「拆礼物」= 这是什么 → 给我的？ → 摇一摇 → 拆开！

> **⚠️ 为什么是"4个故事×4格"而不是"1个故事×16格"？**
> 这是**核心设计教训**（详见 `reference/history-and-troubleshooting.md` 的"单故事注水"坑）。
> 一个小故事的剧情张力**只能支撑 4-6 格**。强行展开成16格会出现：
> - 中段"等待区"全是凑数的过渡词（好期待/忍不住啦/心跳加速…）
> - 尾段情绪高度重复（爱你哟/抱紧紧/最好啦 实质都是"开心+爱"）
> - 用户反馈："有些过于重复了，看来一个小故事只能支撑4-6张图"
>
> 正确做法：**16格 = 4个独立小故事串联**，4行各讲各的，题材多元，零注水。

**角色人设参考**（见 `linkage_scripts.json` 的 `$character_profiles`）：
- 星星布丁：软萌可爱、撒娇精、爱哭鬼、小吃货
- 捞鱼：高冷但宠溺、故作镇定、实际很暖、干饭王
- 周三涵：安静技术宅、害羞、靠谱、默默付出
- 周五涵：活泼话痨、社交达人、爱搞怪、气氛组

**剧本库文件**：`linkage_scripts.json`
- 每组剧本标准 **4 个 panel**（16格加长版可选存 `panels_full` 字段，但默认取 `panels` 前4格）
- 每次生图**随机选 4 组不重复剧本**，拼成4×4（每行一个故事）
- 每个 panel 有 `cn`（中文含义词）、`en`（英文提示词）、`emotion`、`action` 四个字段

**AI创作自由度：**
- 剧本库是**起点**，不是枷锁
- AI 可以在剧本基础上微调情绪、动作，让画面更有趣
- 如果当前弹次有特定主题（节日/季节/情侣），AI 可以设计新剧本
- 新剧本应写入 `linkage_scripts.json` 供后续复用

**剧本池自动补充（必做）：**

每弹生图用掉 4 组剧本后，AI **必须立即补充 ≥4 组新剧本**写回 `linkage_scripts.json`，保持可用池子始终 ≥12 组。

补充规则：
1. 读 `used_linkages.txt` 看哪些已用过（避免重复主题）
2. 设计新剧本：可以从日常生活、情侣互动、网络热梗、季节场景中取材
3. 每组必须有 `id`、`name`、`type`、`link_note`、`panels[4]`（每个 panel 有 `cn`/`en`/`emotion`/`action`）
4. 直接追加到 `linkage_scripts.json` 的 `scripts` 数组末尾
5. 如果池子超过 20 组，可以淘汰最老的已用剧本（从数组前面删除）

**质量检验标准（AI 自检）：**
1. **行独立性**：16宫格的4行，是否各讲各的故事、互不串戏？（视觉复核必查）
2. **每格有料**：随机抽一个 panel，它单独发是否清晰有趣？若发现"等待区"过渡词（闲着/咦？/决定了…），说明这个故事注水了，应改成独立小故事。
3. 生图前问自己：如果把某行的 Panel 1 和 Panel 2 连着发，会不会让聊天对方会心一笑？如果答案是"没什么感觉"，说明联动不够强，需要重新设计。
</linkage-design-system>

<creator-input-contract>
必备输入:
- `config.yaml`
- base 图
- 可用参考图库或关键词库

中间产物:
- `prep_state.json`
- `本次制作角色.md`
- `原图/`
- `原图_透明ChromaKey/`
- `最终版/`
</creator-input-contract>

<creator-known-gap>
当前已知现实:
- `main.py` 仍不应被视为"绝对可靠的一键入口"
- 自动含义词重命名只能基于生成阶段追踪结果,不能替代视觉理解
- skill 文档中凡是写"自动完成",都要以脚本真实行为为准
</creator-known-gap>

<creator-production-log>
### 生产日志审计机制（防漏步）

每弹生成时,各阶段脚本会自动往弹次目录写 `生产日志.md`,记录每步执行结果(状态/时间/关键数据)。

必经步骤(7个,validate pre_publish 会检查是否都 OK):
- `准备` `生图` `含义预检` `透明化` `最终版` `发布素材` `校验`

**为什么需要**:历史上出现过最终版漏跑透明化、带洋红底就发布的严重问题(如第12/13弹)。有了日志,`validate.py --stage pre_publish` 会额外检查 `production_log`,任何必经步骤漏了或失败都会 FAIL,不会漏到成品。

**遇到问题先看哪里**:先打开弹次目录的 `生产日志.md`,哪一步 FAIL/WARN/未执行一目了然。

历史弹次(日志系统接入前生成的)可以用 `production_log.log_step()` 手动补记。
</creator-production-log>

## 快速入口

如果你是第一次执行,按下面顺序走:

1. 运行准备脚本,创建弹次目录、角色卡和 `prep_state.json`
2. 跑生成前校验,确认 base 图、参考图和配置可用
3. 用 Codex 按 4 组宫格图生成表情
4. 裁剪、透明处理、视觉复核、写入 `最终版/`
5. 生成横幅、封面、图标
6. 跑发布前校验
7. 通过后再调用 publisher skill

如果中途失败,只重试当前模块,不要整弹推倒重来。

## 模块化工作流

```
模块0 -> 模块1 -> 关卡1 -> 模块2 -> 关卡2 -> 模块3 -> 关卡3 -> 模块4
准备    生图    校验    后处理    校验    发布素材   最终校验   发布
```

<creator-flow-0-prep>
### 模块0:准备

目标:
- 创建标准目录
- 选模式、角色、衣服和参考图
- 写入 `本次制作角色.md`
- 产出 `prep_state.json`

首选命令:

```bash
cd "E:\星星布丁\微信表情包\.openclaw\skills\lyzbcy-sticker-creator\scripts"
python prep_episode.py --mode auto --type static
```

常见变体:

```bash
python prep_episode.py --mode duo
python prep_episode.py --mode single --character 周三涵
python prep_episode.py --type dynamic
python prep_episode.py --dry-run
```

成功标志:
- 控制台最后一段 JSON 中有 `episode_name` 和 `output_dir`
- 目录里已出现 `参考图/`、`原图/`、`最终版/` 等标准结构
- 已生成 `本次制作角色.md`

失败回退:
- 修 `config.yaml`
- 修 base 图路径
- 修参考图库命名
- 再重跑 `prep_episode.py`

</creator-flow-0-prep>

<creator-flow-1-validate-pre-generate>
### 关卡0:生成前校验

```bash
python validate.py --dir "E:\星星布丁\微信表情包\周三涵做表情N" --stage pre_generate
```

要求:
- base 图存在
- 参考图库路径可读
- Codex CLI 可调用

原则:
- 这一关不过,不进入生图阶段

</creator-flow-1-validate-pre-generate>

<creator-flow-2-generate>
### 模块1:生图

目标:
- 单次生成 1 张 4×4 十六宫格图
- 对应 16 张静态表情
- **16 个 panel 各不相同**：每张参考图天然映射到一个 panel（无需轮换）

执行要求:
- prompt 尽量英文
- 用 stdin pipe 给 codex
- 不写 `transparent background`
- 单次失败只重试
- **AI 可爱度审核**：执行前用 AI 自检 prompt：情绪是否可爱、动作是否容易读懂、是否适合聊天、是否避开生硬/攻击性词。审核不通过就先改 prompt，不直接生图。

生图机制（4×4 单图，省资源）:
- prep 阶段已复制 ≥16 张参考图进弹次 `参考图/` 目录
- `generate_from_prep_state.py` 用 `reference_16grid` 模板，image 1=base，image 2-17=16张参考图
- 16 张参考图分别对应 16 个 panel，天然不重复
- 库里不足 16 张时，自动回退纯提示词模式（16 个去重 emotions）
- 产物：`原图/grid_4x4.png`（单张十六宫格）

最小示例:

```powershell
$codex = "C:\Users\24676\AppData\Roaming\npm\codex.cmd"
$episode_dir = "E:\星星布丁\微信表情包\周三涵做表情N"
$prompt = "..."
$prompt | & $codex exec --enable image_generation --skip-git-repo-check -i "$episode_dir\参考图\base.png" -i "参考图1" ... -i "参考图16"
```

标准命令（推荐）:

```bash
python generate_from_prep_state.py --state "弹次目录/prep_state.json"
# 单次生成 4×4 十六宫格，参考图不足时自动回退纯提示词
```

说明:
- 具体 prompt 模板见 `reference/prompt-templates.md`

</creator-flow-2-generate>

<creator-flow-3-check-generation>
### 关卡1:生图后检查

这一关主要检查"图有没有生成出来",不是最终质量验收。

建议至少确认:
- 4 张宫格图都存在
- 文件不是空的
- 宫格布局没有明显塌掉

如果要正式收口,再走模块2后的 `post_generate` 校验。

</creator-flow-3-check-generation>

<creator-flow-4-postprocess>
### 模块2:后处理

目标:
- 含义预检（识图AI 核对 + 命名）
- 透明处理
- 写入 `最终版/`

执行顺序:

1. **含义预检**：`check_and_rename.py` 把 4×4 单图裁成16个panel + 拼大图 → 识图AI 输出 `_meaning_map.json`
2. 需要透明时做 Chroma-key 到 `原图_透明ChromaKey/`
3. 按 `_meaning_map.json` 重命名为含义词
4. 复制到 `最终版/`
5. （微信上传时会压缩，validate 已放宽到 240-360 都 PASS）

含义预检命令:

```bash
python check_and_rename.py --dir "弹次目录"
# → 产出 原图/_panels/panel_NN.png + 原图/_contact_sheet.png + 打印识图 prompt
# → 用识图AI核对后写回 _meaning_map.json：
python check_and_rename.py --dir "弹次目录" --set '{"1":"含义",...,"16":"含义"}'
```

视觉复核原则:
- 含义词以"图像实际内容"为准（由 check_and_rename 的识图AI 给出建议）
- 文件名控制在 2-4 个中文字符
- 尽量唯一

Chroma-key 和背景策略见 `reference/prompt-templates.md`。



</creator-flow-4-postprocess>

<creator-flow-5-validate-post-generate>
### 关卡2:后处理校验

```bash
python validate.py --dir "E:\星星布丁\微信表情包\周三涵做表情N" --stage post_generate
```

目标:
- 检查目录结构
- 检查尺寸和格式
- 检查含义词
- 检查数量

原则:
- 关卡不通过就停
- 不要把 `WARN` 当 `PASS`

</creator-flow-5-validate-post-generate>

<creator-flow-6-assets>
### 模块3:发布素材

目标:
- 生成 `横幅/`
- 生成 `封面/`
- 生成 `图标/`
- 写入 `介绍.txt`（1-80 字，AI 根据角色、含义词和本弹气质撰写）

首选命令:

```bash
python make_assets.py --dir "E:\星星布丁\微信表情包\周三涵做表情N"
```

要求:
- 横幅 `750x400`
- 封面 `240x240`
- 图标 `50x50`
- 介绍 `介绍.txt`：描述表情特点和故事，不要模板腔，不超过 80 字；发布脚本会优先读取。

回退原则:
- 允许手工挑选最佳成品图重新生成
- 不要硬用效果差的合成图

具体脚本参数见 `reference/scripts-and-assets.md`。

</creator-flow-6-assets>

<creator-flow-7-validate-pre-publish>
### 关卡3:发布前最终校验

```bash
python validate.py --dir "E:\星星布丁\微信表情包\周三涵做表情N" --stage pre_publish
```

至少要确认:
- `sticker_count`
- `sticker_individual`
- `meanings`
- `banner`
- `cover`
- `icon`

如果这里失败,不要进入发布阶段。

</creator-flow-7-validate-pre-publish>

<creator-flow-8-publish>
### 模块4:发布

```bash
cd "E:\星星布丁\微信表情包\.openclaw\skills\lyzbcy-sticker-publisher\scripts"
node publish.js --name "周三涵做表情N" --dir "E:\星星布丁\微信表情包\周三涵做表情N" --type static
```

发布细节见:
- `E:\星星布丁\微信表情包\.openclaw\skills\lyzbcy-sticker-publisher\SKILL.md`

</creator-flow-8-publish>

## 约束脚本速查

| 脚本 | 作用 | 何时用 |
|------|------|--------|
| `prep_episode.py` | 准备弹次、选角色、复制16张参考图、写角色卡 | 开始前 |
| `validate.py --stage pre_generate` | 检查配置、base 图、参考图库 | 准备后 |
| `generate_from_prep_state.py` | 按 prep_state 单次生成 4×4 十六宫格（16参考图天然不重复） | 生图 |
| `check_and_rename.py` | 拼大图+识图AI含义预检，产 _meaning_map.json | 生图后、裁剪前 |
| `crop_grid.py` | 裁剪 2x2 / 3x3 / 4x4 宫格 | 后处理 |
| `make_assets.py` | 生成横幅、封面、图标 | 发布素材阶段 |
| `介绍.txt` | AI 撰写的表情介绍，发布脚本优先读取 | 发布素材阶段 |
| `validate.py --stage post_generate` | 检查目录、尺寸、含义词、数量 | 后处理后 |
| `validate.py --stage pre_publish` | 检查素材、角色卡、赞赏图、生产日志(防漏步) | 发布前 |
| `production_log.py` | 生产日志审计模块(被各脚本自动调用，无需手动跑) | 全流程 |
| `main.py` | 一键流入口,但不应视为唯一可靠入口 | 仅在确认场景适合时使用 |

## 何时看 Reference

只有在当前任务真的需要时再展开细节,不要默认全读。

- `reference/creator-workflow-reference.md`
  适合看:目录结构、角色卡协议、完整流程说明

- `reference/prompt-templates.md`
  适合看:四宫格 prompt、九宫格 prompt、视觉复核 prompt、Chroma-key 和背景策略

- `reference/scripts-and-assets.md`
  适合看:脚本参数、宫格模式、横幅封面图标生成

- `reference/history-and-troubleshooting.md`
  适合看:历史案例、已知坑、测试记录、故障排查

## 推荐执行姿势

如果你是较弱的 AI,按这个最小流程走:

1. 只读本文件前半部分
2. 执行 `prep_episode.py`
3. 执行 `validate.py --stage pre_generate`
4. 仅在需要 prompt 时打开 `reference/prompt-templates.md`
5. 完成后处理再执行 `validate.py --stage post_generate`
6. 完成发布素材再执行 `validate.py --stage pre_publish`

不要先阅读所有历史记录、案例、过时方案和部署文档。

## 明确不推荐的做法

- 不要把旧的 ChatGPT 网页自动化章节当主流程
- 不要默认采用云服务器部署章节
- 不要默认采用 `transparent background` 直出透明图
- 不要跳过视觉复核直接用参考图文件名发布
- 不要把 `main.py` 的历史描述当成当前真实能力

## 当前维护约定

主 `SKILL.md` 只保留:
- 协议
- 快速入口
- 模块流程
- 最小命令
- reference 导航

以下内容应优先放进 `reference/`:
- 长 prompt 模板
- 脚本参数大全
- 背景与 Chroma-key 细节
- 质量经验
- 历史记录
- 故障排查
- 已废弃方案

## Reference 目录

- `reference/creator-workflow-reference.md`
- `reference/prompt-templates.md`
- `reference/scripts-and-assets.md`
- `reference/history-and-troubleshooting.md`

## 结尾提醒

判断一个 AI 是否真正理解了这个 skill,不是看它能不能复述 1700 行文档,而是看它能不能:

1. 先跑准备
2. 知道在哪一关停
3. 需要 prompt 时再去 reference 取
4. 不把历史经验当现行主流程
5. 最后产出可发布的 `最终版/`

