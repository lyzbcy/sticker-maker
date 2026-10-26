# 0.6.5 发版准备 · 2026-10-26

状态：Windows 与 Mac ARM64 候选、隔离验证已完成；未公开发布。源码 0.6.5；另一设备的既有本机升级回执为 0.6.5，本轮未把该回执当作当前 Administrator 设备的实装证明；实时公开版仍为 0.6.2。

## Windows

- 使用本机已有 Python 3.12 虚拟环境、Electron 30.5.1 与 NSIS 缓存重新构建，没有启用历史 Actions 工作流。
- 后端 772 通过、4 跳过、0 失败；桌面 146 通过。Windows 默认测试路径超过本机 MAX_PATH 限制时失败，原日志完整保留；最终用仅作用于测试夹具的短目录及 `\\?\` 前缀运行，未修改业务代码或系统长路径设置。因此通过结果不证明未启用长路径支持的任意深目录都可正常使用。
- 71 个冻结 Python 模块与当前源码语义逐项一致；app.asar 内 14 个桌面构建输入逐字节一致；源码/asar/冻结 IPC 均为 0.6.5。
- 真实打包进程使用合成隔离 userData 完成教程退出、全部表情、问题与警告、系统 Edge 空白页、脱敏诊断导出、正常退出和冷重启，未读取用户作品、未发送反馈或投稿。截图在 `verification/release-prep-0.6.5/ui`。
- 主题安装器：`C:/Users/Administrator/AppData/Local/laoyu-dev-builds/release-prep-065/desktop/release/sticker-maker-win-v0.6.5-setup.exe`，204616215 字节；SHA-256 `dbe413e59365b2b1dec86c571647748645b00b4cb4d10606024a8f9de0fce0a6`。当前设备未安装本次候选。

验证工具修正：`scripts/verify-docx-tasks.cjs` 的期望版本从历史 0.6.2 改为读取当前 package.json，语法检查与真实打包进程验证通过；应用业务文件未改。

## Mac

原生构建设备使用独立缓存目录 `/Users/zeen/Library/Caches/StickerMakerBuilds/0.6.5-prep-20261026`。源快照与最终 529 个输入逐项校验；补入 HTML 入口、同步上述验证工具，并仅对 Mac 的 install.command 规范化 LF。

Python 环境缺依赖，首次直连下载缓慢后停止本任务的 uv 进程，改用清华 PyPI 镜像完成；保留原日志。不搬运安装包回 Windows，仅回传小型报告与截图。Mac 最终结果以 `verification/release-prep-0.6.5/mac` 为准。

Mac 后端含 server 测试 793 通过，前端 146 通过。原生 ARM64 打包、ad-hoc 签名及严格签名检查、隔离真实 UI/IPC、隔离安装及安装后签名检查全部通过；71 个冻结 Python 模块与当前源码语义一致。ZIP 230213241 字节，SHA-256 `2547cd9e94edf98370c6f96a50e09516b16870a0f204e32a85c79a89eb17982b`，位于该 Mac 缓存目录 `candidate/sticker-maker-mac-v0.6.5-local-candidate.zip`。未 Apple 公证，未替换用户实际安装。

## 正式发布前

1. 两端候选已构建并通过上述隔离验证；公开前重新校验制品 SHA，Mac 可将同字节候选 ZIP 以正式命名上传，不重新打包或覆盖同版不同字节。
2. 将候选源码及构建输入锁定到可追溯提交；保留前版回退包和用户数据。当前既有真实 0.6.4→0.6.5 验收在 `09-归档/看板懒加载-20261026`；本轮重新构建的候选不是旧回执中的同一字节安装包。
3. 对最终发行字节验收旧版跨版升级、实际版本/可见重启、入口与数据保留；未验收前不更新公网 version.json。Windows 默认长路径环境限制保持可见，不把测试夹具的解决方式说成产品已修复。
4. 先从各构建设备上传并核验最终不可变资产，再更新 gh-pages 的更新清单与网站；重新查新避免覆盖同版本或落后于其他设备的新发行。GitHub 远端 digest/元数据优先，不重复下载整套包。

待发布说明：`verification/release-prep-0.6.5/release-notes.md`。本轮没有改公网更新源、公开发行或用户的真实作品/评分/账号配置。
