# B. Mac 应用外壳 — 设计文档（Spec）

> **子项目**：B（5 个子项目中的第二个，Mac GUI 外壳）
> **软件对外品牌名**：表情包一键制作
> **状态**：待用户审阅
> **日期**：2026-07-24
> **来源需求**：`.openclaw/初心与使命.md` 第 6-11、14-27、60、74-80 行
> **依赖**：A 核心生图引擎（已交付，main 分支）

---

## 0. 上下文与定位

### 0.1 本子项目职责

把 A 的 Python 核心库包装成**普通人能用的 Mac 桌面应用**：Electron 壳 + Vue 界面，PyInstaller 打包 A，粉丝下载 zip 双击安装即用（免装 Python/node）。对应初心第 3 行"普通用户用不起来，所以打包成软件"。

### 0.2 交付边界

- **交付**：`表情包一键制作.app`（Mac）+ 快捷安装脚本 + electron-builder 打包配置 + GitHub 自动更新/介绍页。
- **不含**：发布能力（C 子项目，B 不预留发布入口）、Win 打包（等稳定后，但架构双端可移植）。
- **验证**：Electron 开发模式跑通全流程 + 打出可双击的 .app（需 node 环境，见 5.3 风险）。

---

## 1. 关键决策记录（9 项）

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| B1 | GUI 技术栈 | **Electron + Web UI** | 双端可移植（初心第 11 行）；你熟悉 Web |
| B2 | JS↔Python 通信 | **子进程 + stdin/stdout JSON-lines** | 流式进度，进程隔离 |
| B3 | 首次向导 | **全流程**（codex/base/模式概率/角色概率/偏好） | 覆盖初心第 14-27 行，一劳永逸 |
| B4 | 更新源 + 介绍页 | **GitHub**（lyzbcy 名下 version.json + Release + Pages） | 复用 lyzbcy-git skill 生态 |
| B5 | Mac 签名 | **无账号，快捷脚本去隔离**（xattr） | 零成本；无 Apple $99/年账号 |
| B6 | Python 打包 | **PyInstaller**（粉丝免装 Python） | 对应初心第 3 行 |
| B7 | 发布入口 | **B 不含**（YAGNI，C 再加） | 不为不存在的功能占位 |
| 架构 | 整体架构 | **方案 1 薄壳 + Python CLI 桥** | 业务逻辑全在 A，Electron 纯展示（初心第 73 行节约 token） |
| 前端 | UI 框架 | **Vue 3** | 轻量、中文生态好、上手快 |

---

## 2. 架构总览

### 2.1 三层结构

```
┌─ 分发产物 表情包一键制作-mac.zip ────────────────────────┐
│  表情包一键制作.app/Contents/                            │
│  ├── MacOS/表情包一键制作        ← Electron 启动器       │
│  ├── Resources/                                          │
│  │   ├── app.asar                ← Electron(Vue+主进程)  │
│  │   ├── sticker-engine-cli      ← PyInstaller 打包的 A  │
│  │   ├── icon.icns                                       │
│  │   └── install.command         ← 快捷安装(双击去隔离)  │
│  └── Info.plist                                          │
└──────────────────────────────────────────────────────────┘
        ↓ 用户首次双击 install.command
   xattr -d com.apple.quarantine（去隔离）+ 拖到 Applications 提示
```

### 2.2 运行时数据流

```
┌─ Electron 渲染进程 (Vue 3) ─────────────┐
│  向导 / 主界面 / 进度条 / 设置 / 结果预览 │
└──────────────┬───────────────────────────┘
               │ Electron IPC (ipcRenderer/ipcMain)
┌──────────────▼ Electron 主进程 ──────────┐
│  PythonBridge: spawn sticker-engine-cli  │
│    管理 stdin/stdout JSON-lines 流        │
│    转发事件给渲染进程                      │
│    处理崩溃/重启                          │
└──────────────┬───────────────────────────┘
               │ stdin(命令) / stdout(事件) / stderr(日志)
┌──────────────▼ A 的 Python（PyInstaller 单可执行文件）─┐
│  sticker_engine/cli.py JSON-lines 路由：               │
│    check_codex / list_characters / generate_base /     │
│    run / stop / save_prefs / list_episodes             │
│  → 复用 StickerEngine API（progress_callback 写 stdout）│
└────────────────────────────────────────────────────────┘
```

### 2.3 设计原则

1. **A 是唯一业务真源**：Electron 不碰业务逻辑，所有计算在 Python。前端只做展示和输入收集。
2. **单进程常驻**：Python CLI 启动后一直读 stdin，避免每次命令重新加载剧本库/关键词库（初心第 73 行节约资源）。
3. **stdout 严格只 JSON**：协议流不能被污染，所有 Python 调试输出走 stderr→日志文件。
4. **双端可移植**：所有平台差异（路径/打包）收拢在 `PythonBridge` 和 `electron-builder.yml`，Vue 界面零平台判断。

---

## 3. JSON-lines 通信协议（B 与 A 的契约）

### 3.1 协议格式

**Electron → Python（stdin，每行一个命令 JSON）：**
```json
{"id":"req-1","cmd":"check_codex"}
{"id":"req-2","cmd":"run"}
{"id":"req-2","cmd":"stop"}
```

**Python → Electron（stdout，每行一个事件 JSON）：**
```json
{"id":"req-1","type":"result","status":"ok","data":{"installed":true,"image_ready":true}}
{"id":"req-2","type":"progress","stage":"S1","message":"调用 codex 中...","percent":0.3,"eta_seconds":180}
{"id":"req-2","type":"progress","stage":"S1","message":"...","percent":0.6,"eta_seconds":90}
{"id":"req-2","type":"result","status":"ok","data":{"episode_dir":"/.../episode_xxx","stickers":16,"meaning_map":{...}}}
{"id":"req-2","type":"result","status":"fail","errors":[...],"aborted_reason":"..."}
```

### 3.2 命令清单

| cmd | 作用 | 返回 |
|---|---|---|
| `check_codex` | 检测 codex 可用性 | CodexStatus(installed/logged_in/image_ready/guidance_msg) |
| `list_characters` | 列出内置角色 + base 图 + 概率 | characters dict |
| `generate_base` | AI 生成新 base 图（J1） | base 图路径 |
| `save_prefs` | 保存前情提要配置 | ok |
| `load_prefs` | 读已有配置（判断首次） | prefs 或 null |
| `run` | 一键生图（主线） | 持续 progress + 最终 Episode |
| `stop` | 取消正在进行的 run | ok |
| `list_episodes` | 列出历史作品 | episode 列表 |
| `open_in_finder` | 在 Finder 打开某弹次目录 | ok |
| `get_version` | 获取本地版本号 | version string |

### 3.3 错误处理

- 协议错误（未知 cmd / JSON 解析失败）→ `{"id":"...","type":"error","message":"..."}`
- Python 进程崩溃 → Electron 主进程检测到退出码非 0，重启 CLI 并通知渲染进程"引擎重启中"
- 长任务期间 stop → Python 置位 stop_event，run 正常返回 aborted Episode

### 3.4 对 A 的改动

A 的 `cli.py` 要从"冒烟脚本"重写成**常驻 JSON-lines 路由器**：
- 读 stdin 循环，每行解析 JSON 命令
- 每个命令映射到 StickerEngine 方法
- `run` 命令的 `progress_callback` 把 ProgressEvent 序列化成 stdout JSON 行
- 所有非协议 print 重定向到 stderr

**这是 B 对 A 的唯一代码侵入**，会改 `sticker_engine/cli.py`，不碰 A 的核心库代码。

---

## 4. 界面结构与状态机

### 4.1 顶层状态机

```
启动 → 读 prefs.yaml
  ├─ 不存在(首次) → 向导(5步) → 写 prefs → 主界面
  └─ 存在 → 主界面
主界面 ⚙设置 ↔ 向导组件(复用) → 保存 → 回主界面
```

### 4.2 向导 5 步

| 步 | 内容 | A 调用 |
|---|---|---|
| 1 codex 检测 | 显示 codex 状态 + 失败时给安装引导（npm i -g codex / codex login） | `check_codex` |
| 2 base 图管理 | 看内置 4 角色及 base 缩略图 / 上传新 base / AI 生成 base | `list_characters` / `generate_base` |
| 3 模式概率 | 单/双/三人/四人概率滑块，提示"建议单人" | 写 prefs.mode_probs |
| 4 角色概率 | 单人模式下各角色占比（依赖步3选了单人） | 写 prefs.single_char_probs |
| 5 生图偏好 | grid(4×4默认)/透明/参考图库优先/故事模式 + 参考图库位置 | 写 prefs + 确认 reference_lib |

向导结束 `save_prefs` 写 `~/Library/Application Support/StickerEngine/prefs.yaml`。

### 4.3 主界面三态

**待机态**：显示当前配置摘要 + "🎨 开始生图"按钮 + 最近作品缩略图（从 `list_episodes`）。

**进度态**（点开始后同屏切换）：进度条（percent）+ 当前步骤（message）+ ETA + 步骤清单（从 production_log）+ [取消]按钮。

**结果态**：16 宫格预览 + 含义词 + [在 Finder 显示][复制到参考图库][再生成一组]。失败时显示 errors + 重试。

### 4.4 设置面板

复用向导步骤 2-5 的 Vue 组件，入口是主界面 ⚙。对应初心"想改随时更改"。

---

## 5. 打包发布链

### 5.1 双阶段打包

**阶段一：PyInstaller 打包 A**
```bash
cd sticker_engine && source .venv/bin/activate
pip install pyinstaller
pyinstaller --onefile --name sticker-engine-cli \
  --add-data "sticker_engine/resources:resources" \
  sticker_engine/cli.py
# 产出 dist/sticker-engine-cli（单可执行文件，含 A + 依赖 + resources）
```
注意：`--add-data` 用 `:` 分隔（Mac），Win 用 `;`——这正是 A 评审遗留 C3（打包 glob）的真正修复点。

**阶段二：electron-builder 打包 .app**
```yaml
# electron-builder.yml
appId: com.lyzbcy.sticker-maker
productName: 表情包一键制作
directories.output: release
mac.target: dir   # 先出 dir，再手动 zip（便于塞 install.command）
extraResources:
  - from: ../sticker_engine/dist/sticker-engine-cli
    to: sticker-engine-cli
  - from: install.command
    to: install.command
```

### 5.2 快捷安装脚本（install.command）

初心第 7-8 行"双击快捷安装自动处理签证"。无 Apple 签名，用去隔离脚本：

```bash
#!/bin/bash
# 双击执行（.command 文件 Finder 可双击）
APP_PATH="$(dirname "$0")/表情包一键制作.app"
xattr -dr com.apple.quarantine "$APP_PATH"   # 去隔离
# 提示拖到 Applications
osascript -e 'display dialog "已去除隔离标记。请将「表情包一键制作」拖到「应用程序」文件夹完成安装。" buttons {"好"}'
```

打包后整个 `.app` + `install.command` 压成 `表情包一键制作-mac-vX.Y.Z.zip` 分发。

### 5.3 GitHub 自动更新 + 介绍页

**版本号**：`package.json` 的 version（如 1.0.0）。A 侧也有 `get_version` 命令读它。

**远端 version.json**（放 lyzbcy 名下某仓库，Pages 服务）：
```json
{"version":"1.0.1","downloadUrl":"https://github.com/lyzbcy/xxx/releases/download/v1.0.1/表情包一键制作-mac-v1.0.1.zip","releaseNotes":"修复..."}
```

**启动检查**（初心第 80 行）：app 启动时 fetch version.json，对比本地 version，不一致弹更新提示，点"一键更新"打开 downloadUrl（或自动下载替换）。

**介绍页**（初心第 74-77 行）：GitHub Pages 静态页，带版本号维护，访问时对比远端版本号强制刷新（前端 JS 检查）。

---

## 6. 目录结构

```
微信表情包/
├── sticker_engine/              ← A（已交付，main）
│   └── sticker_engine/cli.py    ← B 改造为 JSON-lines 路由器
├── desktop/                     ← 【B 新建】Electron 应用
│   ├── package.json             ← electron + vue + electron-builder
│   ├── electron-builder.yml
│   ├── install.command          ← Mac 快捷安装脚本
│   ├── src/
│   │   ├── main/                ← Electron 主进程
│   │   │   ├── index.js         ← 入口
│   │   │   ├── pythonBridge.js  ← spawn CLI + JSON-lines 流管理
│   │   │   └── updater.js       ← 版本检查
│   │   ├── preload/
│   │   │   └── index.js         ← IPC 桥（contextBridge）
│   │   └── renderer/            ← Vue 3
│   │       ├── App.vue
│   │       ├── main.js
│   │       ├── components/
│   │       │   ├── Wizard.vue       ← 向导容器(5步)
│   │       │   ├── WizardStep*.vue  ← 5 个步骤
│   │       │   ├── MainScreen.vue   ← 主界面
│   │       │   ├── ProgressBar.vue
│   │       │   ├── ResultPreview.vue
│   │       │   └── SettingsPanel.vue
│   │       └── store/           ← Pinia 状态管理
│   │           └── engine.js    ← 与主进程 IPC 通信
│   ├── tests/                   ← Vue 组件测试(vitest)
│   └── build/                   ← 打包产物(gitignore)
└── docs/superpowers/specs/2026-07-24-B-Mac应用外壳-design.md（本文）
```

---

## 7. 测试策略

| 层 | 方式 | 覆盖 |
|---|---|---|
| **A 的 CLI 协议** | Python 测试（pytest） | mock stdin 发命令，断言 stdout JSON-lines 正确；run 命令的 progress 流；stop；崩溃恢复 |
| **PythonBridge** | Node 单元测试 | mock child_process，验证 JSON 解析、事件转发、id 关联、重连 |
| **Vue 组件** | vitest + @vue/test-utils | 向导分步流转、进度条渲染、结果预览、失败态 |
| **集成** | spectron/playwright（可选） | 端到端：向导→生图→结果（需真实 codex，手动） |
| **打包** | 手动验证 | PyInstaller 产出可执行 + electron-builder 产出可双击 .app |

---

## 8. 已知边界与风险

### 8.1 B 不做的事

- 不含发布能力（C 子项目）
- 不含 AI agent 接口（D 子项目）
- 不含推广（E 子项目）
- 不做 Win 打包（架构预留双端，Win 等稳定）

### 8.2 风险登记

| 风险 | 等级 | 缓解 |
|---|---|---|
| **本机无 node/npm** | 🔴 高 | Electron 开发和打包必需。Task 0 装 node（brew install node）。**若你拒绝装 node，B 的 GUI 和打包无法在本机完成**——这是硬依赖，必须你确认 |
| PyInstaller 打包体积大（含 numpy/Pillow） | 中 | 预估 30-50MB，可接受；必要时排除未用依赖 |
| codex 在粉丝机上的安装引导体验 | 中 | 向导给清晰步骤；失败时 guidance_msg 来自 A 的 CodexStatus |
| 未签名 .app 被高级安全策略拦截 | 中 | install.command 去 quarantine；极端情况用户需系统设置允许 |
| JSON-lines 协议 stdout 被污染 | 中 | A 的 CLI 入口严格重定向 stderr；加协议自检测试 |
| electron-builder Mac 公证（即便不签名也要 Developer Tools） | 低 | 用 dir target 出包再手动 zip，绕开公证要求 |

---

## 9. 验收标准

1. ✅ `desktop/` 下 `npm run dev` 启动 Electron，能走通向导→生图→结果（需真实 codex）
2. ✅ JSON-lines 协议测试全绿（Python 侧 + Node 侧）
3. ✅ Vue 组件测试全绿
4. ✅ PyInstaller 打出 `sticker-engine-cli` 单可执行，能独立跑 JSON-lines
5. ✅ electron-builder 打出 `表情包一键制作.app`，双击能启动
6. ✅ `install.command` 双击能去隔离
7. ✅ 启动时版本检查能 fetch 远端 version.json 对比（mock 远端测）
8. ✅ 进度条由真实 ProgressEvent 驱动，取消按钮能中断（A 的 stop_event）
9. ✅ 失败态正确显示 errors（Episode.success=False 时）

---

## 10. 下一步

本 spec 用户审阅通过后 → `writing-plans` skill 生成 B 的实现计划。
**实现前置硬依赖**：本机需装 node（brew install node），否则 Electron 开发/打包无法进行。
