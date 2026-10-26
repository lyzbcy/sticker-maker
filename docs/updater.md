> 2026-10-26：正式0.6.6。点击更新与重试均重新查询最新正式清单，锁定版本、平台、URL与SHA；查新失败禁止回落旧缓存，单飞防重复安装。更新查新专项7通过；双端0.6.2→0.6.6最终安装包实际重启、数据保留与回退通过。Windows最后一轮独立桌面，不切换用户桌面；Mac ARM64原生。旧版迁移的测试入口与当前版本查新能力分别记录，未声称远端可以改写旧客户端固化逻辑。见[发行记录](release-0.6.6.md)。

> 现状：稳定（0.6.2已正式发行）
> 负责人：捞鱼工作室 / Codex
> 最后更新时间：2026-10-21

# 更新器

0.6.2正式清单仍使用原URL `https://lyzbcy.github.io/sticker-maker/version.json`；Windows/Mac公开完整下载SHA、选包、受信URL及旧0.5.15/0.5.17更新判断已实际验证，对当前0.6.2不重复提示。网站改用gh-pages静态分支，三个自定义Actions工作流停用；平台内置Pages任务计费0。回执verification/public-release-0.6.2/updater-public-verification.json。本次未执行用户现有安装的替换，不将选包/校验通过冒称真实安装升级通过。

入口desktop/src/main/updater.js；日期update-state.js；Win交接update-handoff.js+install-update.ps1；Mac install.command。

实现：只比较稳定semver，国内连接提示，下载超时/重试、强制受信GitHub包与SHA、单击互斥；Win助手ready/commit/abort握手后退出、等旧PID、备份原目录、真实安装/S /D、FileVersion核对、保留作品、可见重启、结果记录；Mac stage+codesign+原bundle备份替换，不覆盖旧bundle。

已验：单测与真实PowerShell握手（fixture单独标记）；CI38386084597实际官方0.5.0安装→新助手→真实0.5.1安装器→confirmUpdateRestart，版本0.5.1、主程序窗口可见、作品sentinel保留。证据verification/ci-38386084597/distribution-win/real-upgrade.json。

边界：Windows旧版迁移使用新助手测试（不是声称0.5.0旧助手自动被修复）；旧0.5.0客户端需手工安装一次。Windows失败恢复目前为源码/fixture证据，不计为真实失败装机；CI38387951697 Mac真实0.5.0替换、原bundle哈希备份、坏签名拒绝并保留新bundle/作品通过（headless，未算自动可见重启）。最终公开包SHA以release产物为准。
