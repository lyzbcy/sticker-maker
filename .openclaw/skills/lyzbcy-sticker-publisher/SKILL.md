---
name: lyzbcy-sticker-publisher
description: "微信表情包发布工具。按固定流程登录微信表情开放平台并提交表情专辑，强调可校验、可续跑、少猜测。"
---

中文名称：微信表情包发布工具
能力简介：模块化、强约束的微信表情发布 skill，目标是让不同 AI 都能少猜测、少漏步。
使用场景：将创作好的表情包自动提交到微信表情开放平台进行审核发布。

# 微信表情包发布工具 - Sticker Publisher

## AI 统一执行协议

<system-goal>
本 skill 的目标是稳定提交，不是自由探索页面。
所有 AI 都必须把页面当成“固定流程表单”，按既定顺序执行，失败就停并报错。
</system-goal>

<publisher-hard-rules>
1. 先校验，再发布；禁止跳过 validate.py 直接提审。
2. 登录页只走“账号密码登录”，禁止扫码路线。
3. 不要向用户索要账号密码；优先使用已保存登录态或 .env。
4. 每一步优先点精确选择器，其次再做文本回退，不要一上来全局模糊匹配。
5. 中途失败时优先保现场、可续跑，不要刷新后把线索全部丢掉。
</publisher-hard-rules>

<publisher-input-contract>
发布目录应至少包含：
- 最终版/ 或 原图_透明ChromaKey/
- 本次制作角色.md
- 横幅/横幅.png
- 封面/封面.png
- 图标/图标.png
- 介绍.txt（推荐；1-80 字，描述表情特点和故事）

外部固定资源：
- 赞赏引导图.png
- 赞赏致谢图.png
</publisher-input-contract>

<publish-flow-1-validate>
先运行：
python "E:\星星布丁\微信表情包\.openclaw\skills\lyzbcy-sticker-creator\scripts\validate.py" --dir "<表情包目录>" --stage pre_publish
原则：FAIL 不发布；WARN 也要人工确认，不要默认忽略。
</publish-flow-1-validate>

<publish-flow-2-login>
目标：进入后台可操作状态。
顺序：
1. 打开首页
2. 若跳登录页，点击“账号密码登录”
3. 填充已保存账号密码
4. 点击登录按钮
5. 等待出现“提交作品”或离开登录页
失败回退：截图、记录 URL、停止，不要转扫码方案。
</publish-flow-2-login>

<publish-flow-3-form>
目标：按固定顺序填完专辑表单。
关键数据来源：
- 表情图：最终版/ 优先
- 含义词：文件名
- 角色/内容：本次制作角色.md 的“含捞鱼”
- 横幅/封面/图标：各自专用目录优先
</publish-flow-3-form>

<publish-flow-4-submit>
提交前再次确认：
- 图片数量正确
- 含义词无重复
- 免费已选
- 赞赏两张图已上传
只有这些都完成后，才允许点击“提交”。
</publish-flow-4-submit>

<publisher-known-gap>
当前已知现实：
- skill 文档说“发布前必须校验”，但 publish.js 里还没有强制调用 validate.py
- 页面结构变化时，最容易失效的是登录、上传区索引和级联下拉
- 登录成功不应只靠 URL 判断，最好同时结合页面文案校验
</publisher-known-gap>

## ⚡ 发布前强制校验（2026-06-12 NEW）

**发布前必须先跑校验，PASS 才允许发布：**

```bash
python "E:\星星布丁\微信表情包\.openclaw\skills\lyzbcy-sticker-creator\scripts\validate.py" \
  --dir "<表情包目录>" \
  --stage pre_publish
```

**发布准入门槛（必须全部 PASS）：**

| 检查项 | 要求 | 
|--------|------|
| 最终版/ 图片数量 | 16-24 张 |
| 每张图片尺寸 | 240×240 PNG |
| 每张图片透明通道 | RGBA (有alpha) |
| 含义词 | 2-4字中文，无重复 |
| 横幅 | 750×400, 必须存在 |
| 封面 | 240×240 RGBA, 必须存在 |
| 图标 | 50×50 RGBA, 必须存在 |
| 角色卡 | 本次制作角色.md 含「含捞鱼」标记 |
| 赞赏引导图 | 必须存在 |
| 赞赏致谢图 | 必须存在 |

**校验不通过 → 禁止发布 → 修复后重跑校验。**

---

## 🔴🔴🔴 铁律（不可违反，违反即为 BUG）

1. **绝对不要扫码登录**：登录页会显示二维码，但你必须点击"账号密码登录"，走账号密码登录流程
2. **绝对不要问用户要账号密码**：浏览器已保存登录凭据，会自动填入，你只需要点登录按钮
3. **绝对不要让用户手动操作浏览器**：所有操作都由脚本/Puppeteer 自动完成，用户只需等待最终结果
4. **严格按照既定步骤执行**：不得跳步、不得改序、不得省略
5. **每一步都必须点击正确的选择器**：如果某一步找不到对应元素，报错退出，不要猜测

---

## ⚠️ 经验沉淀（2026-06-09）

### 1. 登录持久化
- 脚本使用 `.browser-data` 目录保存登录状态
- 首次登录后，下次运行会自动跳过登录步骤
- 如果需要重新登录，删除 `.browser-data` 目录

### 2. 图片目录自动检测
- 脚本自动检测图片目录，优先级：`最终版` > `原图_透明ChromaKey` > 根目录
- 含义词从文件名自动推导（如"开心比耶.png"→"开心比耶"）

### 2.5 🔴 图片上传顺序（按故事线）
- **上传顺序 = 故事线顺序**：脚本优先读 `<弹次目录>/原图/_meaning_map.json`，按 key（1→16）的顺序排序表情文件后上传
- 多故事架构下 key 1-4=故事A、5-8=故事B…，按此顺序上传，微信面板里**每个故事的表情会连着排**，而不是被打散
- 文件名是纯含义词（无序号），直接 readdir 顺序不可预测，必须靠 meaning_map 还原故事线
- 无 `_meaning_map.json` 时回退到中文文件名排序
- 这样用户在聊天里连发同故事的表情时，面板里挨着点选，体验更好

### 3. 图片上传等待时间
- 图片上传需要时间，脚本根据图片数量动态等待
- 公式：`Math.max(10000, imageFiles.length * 2000)` 毫秒
- 16张图片约等待32秒

### 4. 含义词填写方式
- 使用 `evaluate` 直接设置 `input.value`，比 `type()` 更快更稳定
- 同时触发 `input` 事件让页面识别变化

### 5. 中途出错处理
- **重要**：如果脚本中途出错，页面可能已填写部分内容
- 用户应先点击"保存"按钮，然后刷新页面
- 之后可以用 `upload-icon.js` 连接现有浏览器继续操作

### 6. 图标上传定位
- 图标上传区域是第4个 `input[type="file"]`（索引3）
- accept 属性为 `image/png`

### 7. 连接现有浏览器
- 使用 `puppeteer.connect()` 连接到正在运行的浏览器
- DevToolsActivePort 文件位于 `.browser-data/DevToolsActivePort`
- 用于中途出错后继续操作

---

## 完整发布流程

### 前置条件

- 发布文件夹已存在，如 `E:\星星布丁\微信表情包\周三涵做表情1`
- 文件夹内有透明背景 PNG 表情图（静态）或 GIF（动态）
- 已安装依赖：`cd scripts && npm install`

### 调用方式

```bash
cd "E:\星星布丁\微信表情包\.openclaw\skills\lyzbcy-sticker-publisher\scripts"
node publish.js --name "周三涵做表情1" --dir "E:\星星布丁\微信表情包\周三涵做表情1" --type static
```

参数说明：
- `--name`：表情专辑名称，即文件夹名（如 周三涵做表情1）
- `--dir`：表情图片所在目录的完整路径
- `--type`：表情类型，`static` 或 `dynamic`

---

## 📁 统一文件夹结构规范

**详见：** `E:\星星布丁\微信表情包\.openclaw\skills\README.md`

```
周三涵做表情N/
├── 本次制作角色.md              # ⭐ 角色卡（生成 skill 写入，发布 skill 读取）
├── 参考图/                    # 生成时使用的参考图（可选）
├── 原图/                      # 初始生成的图片
├── 原图_透明ChromaKey/         # Chroma-key处理后的透明背景图
├── 最终版/                    # 最终可发布的版本（含义词命名）⭐
├── 横幅/                      # ⭐ 发布用横幅 (750×400) — publish.js 优先读取
│   └── 横幅.png
├── 封面/                      # ⭐ 发布用封面 (240×240) — publish.js 优先读取
│   └── 封面.png
├── 图标/                      # ⭐ 发布用图标 (50×50) — publish.js 优先读取
│   └── 图标.png
├── 帧图/                      # 动态表情帧图（可选）
└── *.gif                      # GIF成品（可选）
```

### 发布优先级

1. `最终版/` - 最优先（含义词命名，直接可用）
2. `原图_透明ChromaKey/` - 次优先（透明背景，数字命名）
3. `原图/` - 最后（可能有背景问题）

---

## 详细步骤（按既定顺序执行）

### 步骤1：打开登录页

打开 https://sticker.weixin.qq.com/cgi-bin/mmemoticon-bin/readtemplate?t=home/index

如果页面跳转到登录页（URL 包含 `/pages/timeout/login`），则需要登录。

### 步骤2：账号密码登录（全自动，禁止手动干预）

🔴 **严禁扫码！严禁问用户要密码！严禁让用户手动操作！**

具体操作：
1. 页面默认显示的是扫码登录二维码 → **忽略二维码，不要提示用户扫码**
2. 找到并点击 `<span class="active-card">账号密码登录</span>` → 切换到账号密码登录 tab
3. 此时账号密码输入框会出现 → **浏览器已自动填入保存的账号密码，不需要你输入任何内容，也不要问用户要密码**
4. 直接点击 `<button class="weui-desktop-btn weui-desktop-btn_primary">登录</button>` → 完成登录
5. 等待页面跳转到平台主页 → 登录成功

**总结：点击"账号密码登录" → 直接点击"登录"按钮 → 结束。不需要做其他任何事情。**

### 步骤3：点击提交作品

点击 `<button class="weui-desktop-btn weui-desktop-btn_primary">提交作品</button>`

### 步骤4：选择表情专辑

点击 `<a href="/cgi-bin/mmemoticon-bin/pages/stickerPage/detail" class="submit-stiker__type-list-item__container">表情专辑</a>`

现在进入了提交表情专辑页面。

### 步骤5：选择表情类型

- 如果发布静态表情：点击 `<i class="weui-desktop-icon-radio"></i>` 选择静态
- 如果发布动态表情：保持默认或选择动态

### 步骤6：上传表情图片

点击 `<label style="opacity: 0; width: 100%; height: 100%; display: block; cursor: pointer;">` 触发文件选择
选择当前文件夹下的所有表情图片（PNG 或 GIF）
- **顺序重要**：脚本已按故事线顺序（`_meaning_map.json` 的 key 1→16）排序，逐张按此顺序上传，保证微信面板里故事表情连着排

### 步骤7：填写含义词

对每个上传的表情，填写含义词：
- 选择器：`<input class="weui-desktop-form__input" type="text" placeholder="输入含义词">`
- 含义词 = 这个表情的名称
- **注意：同一组表情不可以有相同的含义词**
- 含义词应从文件名推导，如 `开心.png` → 含义词 `开心`

### 步骤8：填写表情专辑名称

选择器：`<input class="weui-desktop-form__input" placeholder="填写表情专辑名称">`
填入当前文件夹名称，如 `周三涵做表情1`

### 步骤9：填写介绍

选择器：`<textarea class="weui-desktop-form__textarea" placeholder="描述表情的特点和故事">`

优先读取表情包目录下的 `介绍.txt`。规则：
- 1-80 字，描述表情特点和故事
- 由 AI 根据角色、含义词、横幅气质撰写
- 不要使用固定模板腔；不要超过平台 80 字限制
- 没有 `介绍.txt` 时，publish.js 使用短默认介绍回退

### 步骤10：填写版权信息

选择器：`<input class="weui-desktop-form__input" placeholder="填写版权信息">`
填写：**捞鱼真不吃鱼**

### 步骤11：上传横幅（⭐ 优先使用 横幅/ 文件夹）

选择器：`<div class="uploader__init"><span class="weui-desktop-icon__add"></span></div>`（第一个）

**自动检测优先级：**
1. `横幅/横幅.png` — ⭐ 由 make_banner.py 生成的专用横幅（750×400，最佳）
2. 自动选择第一张表情图（回退）

**横幅要求（微信平台规范）：**
- 750×400像素，JPG/PNG，>500KB被压缩
- 横图，有张力，色调活泼明朗
- 内容须与表情有关，画面丰富有故事性
- 避免白色背景、避免文字信息

### 步骤12：上传封面（⭐ 优先使用 封面/ 文件夹）

选择器：`<div class="uploader__init"><span class="weui-desktop-icon__add"></span></div>`（第二个）

**自动检测优先级：**
1. `封面/封面.png` — ⭐ 由 make_cover.py 生成的专用封面（240×240，最佳）
2. 与横幅同图（回退）

**封面要求（微信平台规范）：**
- 240×240像素，PNG，>500KB被压缩
- 正面半身像/全身像，最具辨识度
- 透明背景，无白色描边，无锯齿
- 尽量与横幅同一张图

### 步骤13：上传图标（⭐ 优先使用 图标/ 文件夹）

选择器：`<span class="weui-desktop-icon__add"></span>`（图标区域）

**自动检测优先级：**
1. `图标/图标.png` — ⭐ 由 make_icon.py 生成的专用图标（50×50，最佳）
2. 自动选择第一张表情图（回退）

**图标要求（微信平台规范）：**
- 50×50像素，PNG，>100KB被压缩
- 头部正面图像，最具辨识度
- 透明背景，无白色描边，无锯齿
- 无正方形边框，无生硬直角边缘
- 不同专辑用不同图片做图标

### 步骤14：类型细分

选择：`<input type="radio" class="weui-desktop-form__radio" value="1">`
即 **卡通表情/其他**

### 步骤15：角色/内容（⭐ 根据角色卡选择）

**读取 `本次制作角色.md` → 判断含捞鱼？→ 选择对应选项**

1. 点击 `<dt class="weui-desktop-form__dropdowncascade__dt">` 打开下拉
2. 点击 first-level「人物角色」展开二级菜单
3. 在二级菜单中选择：
   - **含捞鱼** → `<div title="人物合辑(包含以上多个)">` 即 **人物合辑(包含以上多个)**
   - **不含捞鱼** → `<div title="女人">` 即 **女人**

### 步骤16：表情风格

勾选以下两项（checkbox）：
- `<input type="checkbox" value="软萌可爱">` → **软萌可爱**
- `<input type="checkbox" value="日常">` → **日常**

### 步骤17：表情主题

选择：`<input type="radio" value="万能通用">`
即 **万能通用**

### 步骤18：下载地区

选择：`<input type="radio" value="DEF">`
即 **全球**

### 步骤19：接受赞赏

勾选：`<input type="checkbox">`（接受赞赏选项）
即打开 **接受赞赏**

### 步骤20：赞赏引导语

选择器：`<input class="weui-desktop-form__input" placeholder="最少填写5个字">`
填写：**谢谢你喜欢我~**

### 步骤21：上传赞赏引导图

选择器：`<div class="uploader__init"><span class="weui-desktop-icon__add"></span></div>`（赞赏引导图区域）
固定路径：**E:\星星布丁\微信表情包\赞赏页\赞赏引导图.png**

### 步骤22：上传赞赏致谢图

选择器：`<div class="uploader__init"><span class="weui-desktop-icon__add"></span></div>`（赞赏致谢图区域）
固定路径：**E:\星星布丁\微信表情包\赞赏页\赞赏致谢图.png**

### 步骤23：提交

点击 `<button class="weui-desktop-btn weui-desktop-btn_primary">提交</button>`

---

## 自动化脚本说明

`scripts/publish.js` 是 Node.js + Puppeteer 自动化脚本，实现了以上完整流程。

### 运行

```bash
cd "E:\星星布丁\微信表情包\.openclaw\skills\lyzbcy-sticker-publisher\scripts"
npm install   # 首次运行安装依赖
node publish.js --name "周三涵做表情1" --dir "E:\星星布丁\微信表情包\周三涵做表情1" --type static
```

---

## 固定配置速查

| 配置项 | 固定值 |
|--------|--------|
| 版权信息 | 捞鱼真不吃鱼 |
| 赞赏引导语 | 谢谢你喜欢我~ |
| 赞赏引导图 | E:\星星布丁\微信表情包\赞赏页\赞赏引导图.png |
| 赞赏致谢图 | E:\星星布丁\微信表情包\赞赏页\赞赏致谢图.png |
| 类型细分 | 卡通表情/其他 |
| 角色/内容 | ⚡ 动态：根据 `本次制作角色.md` 决定（含捞鱼→人物合辑 / 不含→女人） |
| 表情风格 | 软萌可爱、日常 |
| 表情主题 | 万能通用 |
| 下载地区 | 全球 |
| 接受赞赏 | 是 |

---

## 注意事项

1. **不要扫码登录**：必须用账号密码登录方式
2. **含义词不可重复**：每个表情的含义词必须唯一
3. **图标要大头照**：选择人物占比最大的图片
4. **横幅和封面相同**：选择最有吸引力的那张
5. **名称用文件夹名**：如 周三涵做表情1
6. **中途出错先保存**：如果脚本中途出错，先点击"保存"按钮，再刷新页面
7. **登录状态在.browser-data**：删除该目录会清除登录状态

## 常见问题

### Q: 脚本超时报错怎么办？
A: 图片上传和含义词填写可能较慢，脚本已设置5分钟超时。如果仍然超时，检查网络状况。

### Q: 图标上传失败怎么办？
A: 脚本会跳过图标上传继续执行。完成其他步骤后，使用 `node upload-icon.js` 补传图标。

### Q: 如何重新登录？
A: 删除 `scripts/.browser-data` 目录，下次运行会要求重新登录。

---

## 🧪 经验沉淀 (2026-06-09)

### 1. 登录持久化方案

**问题：** 即使使用 `.browser-data` 保存登录状态，微信平台登录仍会过期。用户手动登录后下次重启浏览器可能仍需登录。

**解决方案：** `.env` 文件保存账号密码（Base64 编码），脚本自动填写并登录。

```
# .env 文件内容
WECHAT_STICKER_ACCOUNT=你的账号
WECHAT_STICKER_PASSWORD_ENCODED=Base64编码的密码
```

```javascript
// 解码密码
const PASSWORD = process.env.WECHAT_STICKER_PASSWORD_ENCODED 
  ? Buffer.from(process.env.WECHAT_STICKER_PASSWORD_ENCODED, 'base64').toString('utf8') 
  : '';
```

### 2. 自动登录填写技巧

**问题：** Puppeteer 的 `click()` / `type()` 在某些微信登录页面会报 "Node is not clickable" 错误。

**解决方案：** 使用 `page.evaluate()` 直接操作 DOM。

```javascript
// ✅ 正确：evaluate 直接操作 DOM
await page.evaluate((account, password) => {
  const inputs = document.querySelectorAll('input');
  // 填写账号
  for (const input of inputs) {
    if (input.type === 'text') {
      input.value = account;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    if (input.type === 'password') {
      input.value = password;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }
  // 点击登录
  document.querySelector('button')?.click();
}, ACCOUNT, PASSWORD);

// ❌ 错误：Puppeteer click/type 可能失败
await inputs[0].click({ clickCount: 3 });
await inputs[0].type(ACCOUNT);
```

### 3. 图标补传

**问题：** 图标上传（index 3 的 file input）偶尔失败。

**解决方案：** 
1. 主脚本跳过图标上传继续执行
2. 用 `fix-icon.js` 连接现有浏览器补传图标
3. 使用 `puppeteer.connect()` + DevToolsActivePort 连接

```javascript
const port = fs.readFileSync('.browser-data/DevToolsActivePort', 'utf8').split('\n')[0];
const browser = await puppeteer.connect({
  browserURL: `http://127.0.0.1:${port}`,
});
```

### 4. 自定义简介 / AI 介绍

发布脚本优先读取表情包目录中的 `介绍.txt`、`表情介绍.txt` 或 `description.txt`，并强制校验 1-80 字。

推荐每弹发布前由 AI 写一句自然介绍，例如：
- "四人小队一起上场，委屈、害羞、吐槽和鼓励都软乎乎，适合日常聊天接梗。"

没有介绍文件时，`--theme` 只作为短默认介绍的主题词，不再使用长模板。

---

## 📋 本次制作角色.md（⭐ 生成/发布对齐协议）

### 读取逻辑（publish.js）

发布脚本在步骤15之前调用 `readCharacterCard(dir)`：
1. 检查 `表情包文件夹/本次制作角色.md` 是否存在
2. 解析 `含捞鱼：是/否`
3. 不包含捞鱼 → 步骤15选择「女人」
4. 包含捞鱼 → 步骤15选择「人物合辑(包含以上多个)」
5. 文件不存在 → 默认选「人物合辑」并警告

### 对齐规则

| 含捞鱼 | 角色/内容选择 | 原因 |
|--------|-------------|------|
| **是** | 人物合辑(包含以上多个) | 有男有女，选合辑 |
| **否** | 女人 | 只有女性角色（星星布丁/周三涵/周五涵），选女人 |

---

## 🧪 经验沉淀 (2026-06-10)

### 5. 账号名称更正

**问题：** `.env` 中 `WECHAT_STICKER_ACCOUNT` 之前填的是 `捞鱼真不吃鱼`，但微信平台的登录账号是邮箱 `lyzbcy@qq.com`。

**修正：**
```
WECHAT_STICKER_ACCOUNT=lyzbcy@qq.com
```

### 6. 级联下拉菜单（角色/内容）

**问题：** 步骤15的"角色/内容"是一个**二级级联下拉菜单**，不能直接找"人物合辑"选项。

**正确操作（两步）：**
```javascript
// 第1步：打开下拉，点击 first-level "人物角色"（展开二级菜单）
await page.evaluate(() => {
  document.querySelector('dt.weui-desktop-form__dropdowncascade__dt').click();
});
await sleep(1000);

// 点击 first-level 项目（注意 class 是 ".first-level"）
const firstLevel = await page.$$('.weui-desktop-dropdown__list-ele.first-level');
for (const item of firstLevel) {
  const text = await item.evaluate(el => el.textContent.trim());
  if (text === '人物角色') {
    await item.click(); // 这会展开二级菜单
    break;
  }
}
await sleep(1500);

// 第2步：在展开的二级菜单中点击"人物合辑(包含以上多个)"
const subItems = await page.$$('[title*="人物合辑"]');
if (subItems.length > 0) {
  await subItems[0].click();
}
```

**结构分析：**
- 一级选项 class: `weui-desktop-dropdown__list-ele first-level module-has-options`
- 二级选项 class: `weui-desktop-dropdown__list-ele-contain`（点击后出现）
- 目标：`title="人物合辑(包含以上多个)"`

### 7. fix-icon.js 硬编码路径修复

**问题：** `fix-icon.js` 硬编码了 `周三涵做表情2` 的路径，且自动提交。
**需要修复：** 改为接受命令行参数，去掉自动提交。

### 8. 浏览器占用问题

**问题：** 当第一个 `publish.js` 启动的浏览器还在运行时，再次运行会报 `already running` 错误。
**解决：** 先 `Stop-Process -Name msedge` 关掉所有 Edge，再重新运行。`.browser-data` 会保留登录 session。

### 9. 表情价格选项（新增步骤，2026-06-10）

微信平台新增了"表情价格"选项，需要在提交前选择"免费"：
```javascript
// 选择 radio value="true"（免费）
const priceRadios = await page.$$('input[type="radio"][value="true"]');
for (const radio of priceRadios) {
  const labelText = await page.evaluate(el => {
    const parent = el.closest('label');
    return parent ? parent.textContent.trim() : '';
  }, radio);
  if (labelText.includes('免费')) {
    await page.evaluate(el => el.click(), radio);
    break;
  }
}
```

### 10. 图标提前上传（2026-06-10）

**问题：** 图标上传总是在步骤13失败，因为后续元素遮挡了上传区域。
**解决：** 把图标上传移到流程最前面（步骤6，紧跟在选择表情类型之后），此时页面元素最少，上传区域可正常点击。
- 使用第4个 `input[type="file"]`（索引3，accept=image/png）
- 如果提前上传失败，步骤14会作为备选再次尝试

### 11. 横幅/封面/图标素材文件夹（⭐ 2026-06-10 新增）

**改进：** publish.js 现在会优先从 `横幅/`、`封面/`、`图标/` 文件夹读取专用素材：

```
周三涵做表情N/
├── 横幅/横幅.png   ← 750×400, 由 make_banner.py 生成
├── 封面/封面.png   ← 240×240, 由 make_cover.py 生成
├── 图标/图标.png   ← 50×50,  由 make_icon.py 生成
```

**检测逻辑：** publish.js 自动检测：
1. 横幅：横幅/ 文件夹 → 回退用第一张表情图
2. 封面：封面/ 文件夹 → 回退与横幅同图
3. 图标：图标/ 文件夹 → 回退用第一张表情图

**参考：** 详见 `lyzbcy-sticker-creator/scripts/make_assets.py` 一键生成所有素材。

---

## 🚀 批量发布模式（2026-06-29 新增）

一次性发布几十弹时，单弹 `publish.js` 不够用（每弹启停一次浏览器、90-115秒/弹）。批量模式把任务切成小批自动推进，支持断点续传和失败重试。

### 工具分层

| 脚本 | 职责 | 何时用 |
|------|------|--------|
| `publish.js` | 单弹完整发布（登录→填表→上传→提交） | 发 1 弹 |
| `batch_publish.js` | 单批驱动，把一批弹次逐个发完 | 发 2-5 弹（受 10 分钟超时约束） |
| `batch_all.py` | **总控**：分批 + 断点续传 + 失败重试 | 发 6 弹以上 |

### 快速开始

```bash
cd "E:\星星布丁\微信表情包\.openclaw\skills\lyzbcy-sticker-publisher\scripts"

# ① 发布一整段（默认弹19-54，自动每5弹分批、跑完自动重试失败的）
python batch_all.py --start 19 --end 54

# ② 中途被超时打断？续传（跳过已成功的，只补剩余 + 重试失败）
python batch_all.py --start 19 --end 54 --resume

# ③ 只发指定几弹（重发失败弹次常用）
python batch_all.py --only 23,51,53

# ④ 调整分批大小和弹间间隔
python batch_all.py --start 19 --end 54 --batch 5 --gap 8 --retry 2
```

### 参数说明（batch_all.py）

| 参数 | 默认 | 说明 |
|------|------|------|
| `--start` / `--end` | 19 / 54 | 发布范围 |
| `--only` | - | 指定弹次（逗号分隔，优先于 start/end） |
| `--resume` | 关 | 续传：跳过 `_batch_total.json` 里已 OK 的弹次 |
| `--batch` | 5 | 每批弹数（**不要超过 5**，否则单批会超 10 分钟被杀） |
| `--gap` | 8 | 弹间间隔秒数（给平台喘息，降低风控） |
| `--retry` | 2 | 全部跑完后，对失败弹次自动重试次数 |

### 断点续传原理

- `_batch_total.json`：跨批次累积结果（断点续传的依据）
- `_batch_result.json`：`batch_publish.js` 当批输出（每批覆盖）
- 每批结束立即合并到 `_batch_total.json` 并保存 → **即使被超时杀掉，已完成批次不丢**
- `--resume` 会跳过已 OK 的弹次，从断点继续

### 结果文件

- `_batch_total.json`：本次批量发布全量结果（成功/失败清单）
- `batch_publish_results.json`：上一次批量发布的归档结果（手动留存）

### ⚠️ 批量发布注意事项

1. **每批≤5弹**：单弹约 90-115 秒，5 弹≈10 分钟，卡在外层超时上限。大批量必须用 `batch_all.py` 自动分批。
2. **登录态**：首次会触发 `publish.js` 自动登录（用 `.env` 凭据），无需人工扫码。登录态存在 `.browser-data/`，之后自动复用。
3. **失败重试**：赞赏图上传偶发失败（见下方经验），`batch_all.py` 会自动重试 `--retry` 次。稳定失败的（如校验不过）需人工修。
4. **平台风控**：连续提交几十弹理论上可能触发频率限制，`--gap` 间隔能缓解。如遇风控，加大间隔或分多次跑。
5. **校验前置**：`publish.js` 发布前会跑 `validate.py`，**生产日志的必经步骤缺失会直接拒发**（见 troubleshooting「校验拦截」）。

---

## 📝 经验沉淀（2026-06-29 批量发布实战）

### 12. 赞赏图上传：必须验证，否则假阳性（⭐ 重要）

**坑：** 早期赞赏图上传用 `waitForFileChooser + input.click()`，并按"倒数第2个=input"猜索引。结果：
- fileChooser 选错 input（8 个 input 里赞赏图实际是第 4、5 个，不是倒数 2 个）
- 传错位置还报"上传成功" → 提交后平台因赞赏图缺失打回 → **假阳性**

**修复（publish.js 步骤 23/24）：**
1. **标签定位**：逐个 `input[type="file"]` 向上找祖先文字，匹配"赞赏引导图"/"赞赏致谢图"，定位准确 input
2. **用 uploadFile**：`elementHandle.uploadFile(path)` 比 fileChooser 可靠（横幅/封面/图标一直用这个，从没出问题）
3. **缩略图验证**：上传后检查 `[class*="uploader"] img` 数量是否增加，没增加就判失败（不再假阳性）

### 13. 赞赏图裁剪框：uploadFile 后要点"确定"

**坑：** 某些弹次上传赞赏图后，平台弹出"裁剪...取消/确定"对话框。`uploadFile` 只是选了文件，**没点"确定"裁剪就不生效**，缩略图不出现 → 验证失败 → 该弹被反复判失败（弹51连续失败3次就是这个原因）。

**修复：** `uploadFile` 后检测裁剪框，自动点"确定"：
```javascript
const cropConfirmed = await page.evaluate(() => {
  const ok = Array.from(document.querySelectorAll('button, a.weui-desktop-btn'))
    .find(b => (b.textContent||'').trim() === '确定' && b.offsetParent !== null);
  if (ok) { ok.click(); return true; }
  return false;
});
```

### 14. 封面图不要复用横幅图（⭐ 重要）

**坑：** `make_assets.py` 调 `make_cover(cover_img, out, banner_ref=banner_img)`，而 `make_cover` 优先用 `banner_ref` 作源图 → **封面实际是横幅那张图**，构图是横幅的横向拼贴，不是封面该有的单角色特写。弹21起全部受影响。

**修复：** `make_assets.py` 第 120 行去掉 `banner_ref`：`make_cover(cover_img, cover_out)`。封面直接用 `pick_best_image('cover')` 选的成品图。

**教训：** 封面和横幅是两种用途，封面要"最具辨识度的单角色正面特写"，横幅是"横向宽幅展示"，绝不能共用源图。

---

*Sticker Publisher Skill - Created by 周三涵*
