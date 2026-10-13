> 现状：稳定（0.5.1已正式发行）
> 负责人：Codex
> 最后更新时间：2026-10-13

# 技术方案

桌面通过 preload 受控 IPC 与常驻 Python JSON-lines 引擎通信。引擎使用 STICKER_ENGINE_USER_DATA 做测试隔离；发行包必须包含 Python runtime、keyring 与 Playwright 浏览器。Codex 是外部依赖，先检测安装与登录；开发机已登录不等于粉丝免登录。日志：阶段/时间/消息，用户能查看和复制；反馈脱敏路径与令牌。每日更新口径 Asia/Shanghai，尝试与成功分开记录。
