# B Mac 应用外壳 · 完成度与技术债

> **何时读**：要看 B 做到哪了、有哪些坑没填。

## 完成度：可交付

- Electron + Vue 3 完整实现（脚手架/主进程/PythonBridge/向导/主界面/进度/结果/设置）
- A 的 cli.py 改造为 JSON-lines 路由器（常驻、多线程不阻塞 stdin）
- PyInstaller 打 sticker-engine-cli（27MB，含 A+resources，4 角色加载验证通过）
- electron-builder 打出 `表情包一键制作.app`（arm64）
- zip 分发包：`desktop/表情包一键制作-mac-v0.1.0.zip`（301MB，含 .app + install.command）
- install.command 双击去隔离（无需 Apple 签名，B5 决策）
- 自动版本检查（updater.js，fetch 远端 version.json）

## 测试

- A Python：85 passed（含 CLI JSON-lines 6）
- B PythonBridge：5 passed（vitest）
- vite build：47 模块通过
- electron-builder：.app 启动验证通过（进程存在）

## 已修复的 Critical（评审发现）

- **C1** ✅ cli.py main() 改多线程，run 不阻塞 stdin，stop 能真正中断
- **C2** ✅ PythonBridge 追踪 currentRunId，stop 缺省 target 时停当前 run
- **C3** ✅ PythonBridge 崩溃自动重启（_stopped 标记区分主动关闭）
- **I2** ✅ savePrefs 前端先校验 mode_probs 总和
- **I4** ✅ clearResult() 让结果态能回待机态

## 遗留技术债（按优先级）

### 需真实 codex 端到端验证

| # | 问题 | 说明 |
|---|---|---|
| 真实生图 | 没有真实 codex 跑过完整向导→生图→结果 | 代码逻辑就绪，需用户有 codex 时验证 |
| I6 | stop 检查粒度（A 侧 runner 只在阶段间检查） | codex 生图期间无法立即取消，等当前调用返回。A 的限制，记录在 A 的 status |

### 后续迭代

| # | 问题 | 说明 |
|---|---|---|
| I1 | dev 模式 Python 路径硬编码本机绝对路径 | `pythonBridge.js:25`，换机器/CI 要改。打包模式不受影响 |
| I3 | 引擎启动失败时无整体错误态 | 直接进向导，check_codex 失败但无降级提示 |
| Vue 组件测试 | `tests/components/` 空 | spec §7 要求的向导流转/失败态组件测试未补 |
| WizardStepBase | 上传/AI 生成 base 是占位 | B 范围控制，当前只显示内置角色 |
| 介绍页 GitHub Pages | updater 只做 version.json 检查 | 静态介绍页 HTML 未做（初心第 74-77 行） |

## 分发

- **产物**：`desktop/表情包一键制作-mac-v0.1.0.zip`（301MB）
- **用户流程**：解压 → 双击 install.command（去隔离）→ 拖到 Applications → 启动
- **依赖**：用户需自备 codex CLI（首次向导 step1 检测 + 引导安装）
