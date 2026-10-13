---
name: sticker-maker-dev
description: 表情包一键制作开发、测试与分发入口。
---
# 表情包一键制作
## 项目一句话
给粉丝制作自己的表情包；生成与微信平台发布是两个独立动作。
## 技术栈
Electron 30 / Vue 3 / Pinia / Python 3.12 / PyInstaller；Windows x64 与 macOS ARM64。
## 目录地图
- desktop/src：主进程、预加载与界面；desktop/site：介绍与更新清单。
- sticker_engine：JSON-lines 引擎与后端测试。
- docs/agent.md：唯一开发导航；doc/：历史专题资料。
- reference/standards：项目自包含规范快照。
- verification：原始哈希、回归结果与验收证据。
## 开发流程
1. 先读 docs/agent.md、roadmap.md 和对应模块文档，再读 .agents/skills/sticker-maker-dev/SKILL.md 的引擎纪律。
2. 保留现有未提交代码与真实用户数据；小写英文文件名；fix/feat/docs 提交；按既定仓库分支协作；备份源码不等于发布安装包。
3. 代码、文档、版本同步：desktop/package.json、package-lock.json、Python pyproject.toml 与 cli.py；正式包确认后再更新网站 version.json，严禁伪造新包哈希。
4. 日志显示阶段/输入输出/耗时；反馈只发送经脱敏的信息。
5. 发版读 reference/standards/启动器适配/laoyu-launcher-adapter/SKILL.md 与 docs/distribution.md。
## 功能现状与验收入口
详细逐项状态见 docs/audit.md；测试：desktop/npm test、sticker_engine/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/agent。
自身更新与首次迁移见 docs/updater.md；启动器产品 ID 为 sticker-maker，主程序为 表情包一键制作.exe。
## 红线
不覆盖个人作品库、凭据、微信登录状态。不得绕过角色身份检查、提交成功判据与资源库锁。
更新器变更先记录原因与测试；新包先校验再安装，失败保留旧版和设置。
## 当前状态
当前正式版本0.5.1；双平台Release与官网已更新，具体验收与边界见docs/audit.md及roadmap.md。源码版本不能代替真实产物的版本与哈希。
