> 现状：稳定（0.5.1已正式发行）
> 负责人：捞鱼工作室 / Codex
> 最后更新时间：2026-10-13

# 更新器

入口desktop/src/main/updater.js；日期update-state.js；Win交接update-handoff.js+install-update.ps1；Mac install.command。

实现：只比较稳定semver，国内连接提示，下载超时/重试、强制受信GitHub包与SHA、单击互斥；Win助手ready/commit/abort握手后退出、等旧PID、备份原目录、真实安装/S /D、FileVersion核对、保留作品、可见重启、结果记录；Mac stage+codesign+原bundle备份替换，不覆盖旧bundle。

已验：单测与真实PowerShell握手（fixture单独标记）；CI38386084597实际官方0.5.0安装→新助手→真实0.5.1安装器→confirmUpdateRestart，版本0.5.1、主程序窗口可见、作品sentinel保留。证据verification/ci-38386084597/distribution-win/real-upgrade.json。

边界：Windows旧版迁移使用新助手测试（不是声称0.5.0旧助手自动被修复）；旧0.5.0客户端需手工安装一次。Windows失败恢复目前为源码/fixture证据，不计为真实失败装机；CI38387951697 Mac真实0.5.0替换、原bundle哈希备份、坏签名拒绝并保留新bundle/作品通过（headless，未算自动可见重启）。最终公开包SHA以release产物为准。
