> 现状：0.6.2双端本地候选已验收；公网版本独立维护
> 负责人：Codex
> 最后更新时间：2026-10-21

# 技术方案

桌面通过 preload 受控 IPC 与常驻 Python JSON-lines 引擎通信。引擎使用 STICKER_ENGINE_USER_DATA 做测试隔离；发行包包含 Python runtime、keyring 与 Playwright库/驱动，0.6.2起默认不重复内置浏览器，优先使用系统Edge/Chrome，缺少时按需安装组件。Codex 是外部依赖，先检测安装与登录；开发机已登录不等于粉丝免登录。日志按[本地诊断规范](logging.md)缓冲写入、轮转、脱敏并支持导出；每日更新口径 Asia/Shanghai，尝试与成功分开记录。双平台共用业务源码，按用户要求在Windows本机和SSH连接的Mac原生本地打包，不使用Actions，详见[架构与改版记录](desktop-usability-20261021.md)。
