# 表情包概率控制台 — 架构理解与修改记录

> 周三涵 (2026-06-11) · 为捞鱼而写

---

## 一、我对这个前端的理解

### 它是什么

这是一个**可视化的概率微调面板**，塞在 `lyzbcy-sticker-creator` skill 里，通过浏览器界面实时调整表情包生成系统中所有随机变量的权重，然后一键写回 `config.yaml`。

不用打开 YAML 文件手改数字，不用心算比例，不用重启脚本验证。

### 它解决什么问题

`lyzbcy-sticker-creator` 是一个全自动表情包工厂——从选角色、选衣服、选参考图、拼 prompt、调 ChatGPT 生图、裁剪、抠图到发布，一条龙。但这里面有大量的**随机选择**：

| 随机环节 | 配置项 | 为什么需要调 |
|----------|--------|-------------|
| 模式 | `mode_probabilities` (单人/双人/四人) | 今天想多出双人贴贴，少出单人 |
| 角色 | `single_character_probabilities` | 星星布丁是不是出太多了，该多出周三涵 |
| 衣服 | `character_costume_probabilities` | 新做了 base6，想让它多出场 |
| 参考图 | `reference_probabilities` | 有些参考图表情不好看，暂时不用 |
| Prompt | `keywords.json` (动作+情绪) | 加新动作/情绪关键词，丰富 prompt 素材 |

数量一多，YAML 手改就非常痛苦。这个控制台把这些数字变成**拖滑块、打勾、点按钮**的操作，视觉上立刻能看到概率分布。

### 用户（捞鱼）的核心意图

捞鱼想要一个**实时可调节的仪表盘**——不是一次性配置，而是日常创作中的「调音台」：

1. **新衣服自动发现**：加一张 `星星布丁base7.png` 到磁盘 → 刷新页面自动出现在卡片里，标 🆕，自动分配概率
2. **参考图画廊管理**：预览所有参考图，勾选参与/排除，不要的可以直接删
3. **策略存档**：像游戏一样存 3 个档位 —— "今天主出双人模式"、"全自动默认"、"测试新衣服概率" —— 一键切换
4. **Prompt 词库维护**：动作列 + 情绪列的连连看式管理，可以加自定义列（如"场景"、"物体"）

---

## 二、技术架构

```
浏览器 (index.html) ←HTTP→ Node API Server (server.js, 端口3412)
                               ↓ 读写
                         config.yaml + keywords.json + strategies/slot*.json
```

### 服务端 (server.js)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 返回静态 HTML 页面 |
| `/api/config` | GET | 返回完整视图数据（模式/角色/服装/参考/关键词） |
| `/api/image?path=...` | GET | 从磁盘读取并返回图片（用于缩略图预览） |
| `/api/probabilities` | POST | 保存概率数据到 config.yaml |
| `/api/keywords` | POST | 保存 prompt 关键词到 keywords.json |
| `/api/reset` | POST | 重置所有概率为默认均分 |
| `/api/strategies` | GET | 返回 3 个存档位的状态 |
| `/api/strategies/save?slot=N` | POST | 保存当前配置到指定存档位 |
| `/api/strategies/load?slot=N` | POST | 从存档位加载配置到当前 |
| `/api/strategies/delete?slot=N` | POST | 删除存档位 |
| `/api/ref/delete` | POST | 从磁盘删除参考图文件+配置条目 |

### 关键函数（服务端）

- **`buildView(config)`** — 核心：读 config.yaml + 磁盘扫描 → 合并生成前端所需的数据结构
- **`scanDiskBases()`** — 扫描 `E:\星星布丁\微信表情包\` 下的 `{角色}base{N}.png/jpg` 文件
- **`scanRefImages()`** — 扫描 `参考图库/` 目录
- **`mergeBaseImages()`** — 磁盘发现与 config 已有条目合并，标记新发现
- **`writeConfig()`** — 将 JS 对象写回 YAML，保留注释和结构

### 前端 (index.html)

单页 HTML，包含内联 CSS 和 JS，无需构建工具。

**渲染流程：**
```
loadData() → GET /api/config → render(data) → 生成 HTML → 插入 DOM → updateAllBars()
```

**交互流程：**
```
滑块拖动 → onSlider() → 同组自动归一化（0值保持，非0值比例调整）
参考图勾选 → toggleRef() → 即时保存到 config.yaml
保存全部 → saveAll() → 收集所有值 → POST /api/probabilities
存档加载 → loadStrat(N) → POST /api/strategies/load?slot=N → loadData() 刷页面
```

### 自动归一化算法

这是前端最精巧的一段逻辑：

1. 用户拖动某个滑块
2. 收集同组所有滑块的当前值
3. 记录哪些是 0（用户明确设零）
4. 计算需要调整的量：`delta = 新总量 - 旧总量`
5. 等比例分配给所有非零滑块（`新值 = 旧值 × (目标总和 / 当前非零总和)`）
6. 保持 0 值不动，四舍五入到整数百分比

这样用户只需要关心"谁多谁少"，不需要手动算总数。

---

## 三、修改记录（按时间线）

### 第一轮 (6/11 上午) — 基础搭建

| 改动 | 说明 |
|------|------|
| 创建 frontend 目录 | server.js + public/index.html + package.json |
| 8 卡片布局 | 模式概率、角色概率、参考图概率、4 个服装卡片、AI Prompt 配方 |
| 磁盘扫描 | 自动发现 `{角色}base{N}.png/jpg`，标 🆕 |
| 参考图缩略图 | 26 张参考图 + 概率滑块 |
| 策略存档 | 3 个存档位 save/load |
| zeen-tools 脚本 | 一键启动/关闭 bat，UTF-8 BOM + CRLF |
| 端口安全杀进程 | 只杀 3412 端口的进程，不杀所有 node |

### 第二轮 (6/11 下午 17:30) — Bug 修复 + 体验重做

| 改动 | 原因 |
|------|------|
| 滑块自动归一化 | 用户反馈「合计不自动变 1」 |
| 参考图改为画廊模式 | 参考图是顺序使用（非概率采样），不需要概率。改为 ☑️ 勾选 + 灰显 + 删除 |
| 修复 saveAll NaN 污染 | 参考图改成 checkbox 后，`parseInt("on")` = NaN，写进 config.yaml 全坏 |
| 修复 extra_cols 不渲染 | addTag/rmTag 只支持顶层 key，额外列的 items 在嵌套数组里 |
| 策略存档重做 | 6 个简陋按钮 → 三卡片游戏式存档（名称/时间/摘要/加载/覆盖/删除） |
| 修复 `html is not defined` | 替换策略栏时 `let html=` 误写为 `html+=`，丢失声明 |
| 清理 server.js 重复代码块 | 早期编辑残留导致语法错误 |

### 核心 Bug 复盘

**NaN 污染链路（最严重的 bug）：**
```
参考图从 slider 改为 checkbox
    → toggleRef() 即时保存：值=0/1 ✅ 正常
    → 但 saveAll() 仍然用 collect('ref','[data-ref]')
    → collect() 里 parseInt(checkbox.value) → parseInt("on")=NaN
    → POST {reference_probabilities: {xxx: NaN, yyy: NaN}}
    → 服务端 NaN 校验失败未被拦截（NaN > 0.015 = false）
    → writeConfig() 里 NaN.toFixed(2) = "NaN"
    → config.yaml 被写成:
      reference_probabilities:
        "双人抱.png": NaN
        "偷吃.png": NaN
    → YAML 解析失败 → 整个 skill 崩溃
```

**修复方案：**
- 前端：saveAll 不再收集 reference_probabilities（参考图通过 toggleRef 独立保存）
- 服务端：移除 reference_probabilities 的 sum=1 校验，增加 NaN 清洗逻辑
- 服务端 writeConfig：对 reference_probabilities 值做 `isNaN` 防护

---

## 四、设计决策

### 为什么磁盘扫描优先于 config

config.yaml 可能过时（扩展名 .jpg vs 磁盘 .png），或者磁盘有新增文件未写入 config。磁盘扫描作为 source of truth，config 只补充概率数据。

### 为什么新增变体自动均分

不预设偏好的变体（如新加的 base7），全部均分 -> 用户可以手动调整并保存。这样不会因为某个新变体概率=0 而永远不会被用到。

### 为什么策略存档用独立 JSON 而非塞进 config

config.yaml 是主配置，策略存档是快照。独立文件：
- 不会污染 config
- 加载/保存互不干扰
- 数据结构可以不同（存档有 name/timestamp）

### 为什么参考图不设概率

参考图系统的工作方式是**顺序使用**（按库存顺序排），不是**随机抽样**。概率在参考图层面上没有意义——参考图要么参与（勾选）要么不参与（取消勾选）。

---

## 五、待办 / 已知限制

- [ ] Chrome key 颜色选择器（暖色角色用绿色 key，正常角色用洋红 key）
- [ ] 存量管理视图（已用参考图标记，避免重复）
- [ ] 生成历史日志（哪次用了哪些配置）
- [ ] 存档预览对比（加载前 diff 显示差异）
- [ ] 移动端响应式优化（当前卡片在小屏上布局拥挤）

---

## 六、文件清单

```
E:\星星布丁\微信表情包\.openclaw\skills\lyzbcy-sticker-creator\frontend\
├── README.md               ← 本文件
├── server.js               ← Node API 服务端 (端口3412)
├── package.json             ← js-yaml 依赖
├── public/
│   └── index.html          ← 主界面（单文件，内联 CSS+JS）
├── strategies/
│   ├── slot1.json          ← 存档位1
│   ├── slot2.json          ← 存档位2
│   └── slot3.json          ← 存档位3
├── zeen-tools/
│   ├── 一键启动前端.bat     ← 双击启动
│   └── 一键关闭前端.bat     ← 双击关闭
├── check.js                ← 验证脚本（旧）
├── check_v3.js             ← 验证脚本 v3
└── verify.js               ← 验证脚本
```

### 关联文件（非本目录）

| 文件 | 作用 |
|------|------|
| `../config.yaml` | 主配置，mode/character/costume/reference 概率 |
| `../keywords.json` | Prompt 关键词库（actions/emotions/extra_cols） |
| `../SKILL.md` | skill 主文档 |

---

*周三涵写于 2026-06-11 · 捞鱼的第 N 次前端折腾*
