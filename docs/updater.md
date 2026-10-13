> 现状：验收中（未正式发布）
> 负责人：捞鱼工作室 / Codex
> 最后更新时间：2026-10-13

# 更新器

入口desktop/src/main/updater.js；日期update-state.js；Win交接update-handoff.js+install-update.ps1；Mac install.command。

实现：只比较稳定semver，国内连接提示，下载超时/重试、强制受信GitHub包与SHA、单击互斥；Win助手ready/commit/abort握手后退出、等旧PID、备份原目录、真实安装/S /D、FileVersion核对、保留作品、可见重启、结果记录；Mac stage+codesign+原bundle备份替换，不覆盖旧bundle。

已验：单测；真实PowerShell握手（verification/handoff-result.txt）只使用fixture worker，不等价实际安装。真实下载校验包已构建。

未验：从真实旧版到新版、新版窗口可见及confirmUpdateRestart、注册表、失败恢复实际安装。必须完成干净机器QA后发版。旧0.5.0没有新交接功能，需手工安装一次。
