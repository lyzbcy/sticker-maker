---
name: sticker-maker-dev
description: 表情包一键制作的软件开发、排障、测试与分发入口。
---

# 表情包一键制作 · 开发入口
现状：源码/本设备Windows/公开正式0.6.13；11-05 双端正式发行与本机升级结果见 docs/current-state.md。
负责人：捞鱼工作室 / Codex
最后更新时间：2026-11-05

## 项目与技术栈
为用户制作、整理、导出表情包；生成、视觉质检、微信投稿、平台身份核验分别验收。
Electron30 / Vue3 / Pinia / Python / PyInstaller，Windows x64、macOS ARM64。开发Python按本机已有环境，不能假称项目不存在的.venv已安装。

## 按需入口

QQ投稿、精选JSONL分发、抖音使用量与收益核查：读[QQ流程](.openclaw/skills/lyzbcy-sticker-publisher/reference/qq-publish.md)与[分发数据规则](.openclaw/skills/lyzbcy-sticker-publisher/reference/distribution-analytics.md)。使用已验证的发布skill分支；不因此启动客户端改版或为独家平台默认重做精选。


抖音静态表情投稿与接口自动化：读[投稿流程](.openclaw/skills/lyzbcy-sticker-publisher/reference/douyin-publish.md)，脚本在 `.openclaw/skills/lyzbcy-sticker-publisher/scripts/douyin_publish.py`。这是创作skill的发布分支；不更改桌面客户端或版本。

1. 开发任何功能前先查[开发导航](docs/agent.md)与对应模块；没有模块文档先建。
2. 版本、设备状态与证据只认[当前状态](docs/current-state.md)，计划见[roadmap](docs/roadmap.md)。
3. [架构](docs/tech.md)、[开发不变量](doc/reference/development-invariants.md)、[长任务续接](docs/long-task-handoff.md)。

## 目录地图
- desktop/src：主进程、preload、Vue界面和store；desktop/site：网站/正式更新清单。
- sticker_engine：JSON-lines引擎与后端测试；scripts：已有安装操作驱动。
- docs：模块知识库；doc/reference：深度细节；doc/history：历史，不作为当前设备事实。
- reference/standards：自包含规范；verification：历史回执；launcher-adapter.json：启动器产品描述。

## 开发约定
- 不覆盖其他聊天修改，不移动正在运行的安装、素材或同步服务目录。功能先按原哈希保护，再测试副本/失败/回滚。
- 代码、对应文档、版本同步；只改文档不抬程序版本。按[日志规范](reference/standards/软件组件/日志系统.md)维护队列、轮转、退出刷写、排障开关与真实进度。
- 现有原组件DOM/data-test、任务语义、未知结果核销和数据路径按模块约定保留；错误不得变成假成功。
- 小步开发按项目既有提交/分支约定备份；不新建远端，不自动改变可见性。公开发版按已有授权流程，不把未公开开发包写入公网清单。

## 版本与交付
四处：desktop/package.json::version、desktop/package-lock.json::version/packages[""].version、sticker_engine/pyproject.toml::project.version、sticker_engine/sticker_engine/cli.py::VERSION。
普通开发累计约2～3个完成版本再合并公开，非凑版本；功能完成须本设备原位升级并核对实际路径/可见版本/冷重开/数据保留。优先本地构建，不上传再下载。源码、本机、公网版本分开记录，其他设备验收独立。
更新器红线详见[updater](docs/updater.md)与[规范](reference/standards/软件组件/自适应更新检测.md)：点击重新查新、锁同一目标、旧缓存跨版与重启核对。未验不能勾完成。

## 功能现状与验收入口
- 资源库8视图与取消目录/单飞/卸载清理：见[资源库重构](docs/resource-library-refactor-067.md)，0.6.7已本机升级。
- 引擎事件/任务结束状态/反馈复制：见[事件生命周期](docs/engine-event-lifecycle.md)，0.6.9修复主进程真实命令收尾、设置初始化误保存与资源读取错误恢复；本机门槛已验，详见模块。
- 日志：[logging](docs/logging.md)；反馈：[feedback-service](docs/feedback-service.md)；AI接入：[本地规范](reference/standards/软件组件/AI-Native.md)，接口说明在sticker_engine/sticker_engine/agent/AGENT_PROMPT.md。
- 启动器：稳定ID sticker-maker / 主程序“表情包一键制作.exe”；[本地适配规范](reference/standards/启动器适配/laoyu-launcher-adapter/SKILL.md)。根描述文件仍为历史0.5.1正式制品，不冒称已登记本开发包；公开发版前须按实际正式包刷新并严格自查。
- 前端在desktop执行npm.cmd test；后端在sticker_engine用已有Python执行python -m pytest tests -q --ignore=tests/agent。临时数据/APPDATA必须隔离；完整回执见docs/current-state.md，不以mock代替真实安装。

## 红线
保护角色身份门禁、账号校验、资源库锁、投稿完整性与未知结果核销；已成功/未知投稿不盲重试。人工/AI评分缺失为null，不用质检分替代。作品、原图、评分、账号、设置及待审状态不得为重构而改写。
签名、更新器、服务端密钥、正式制品只按专门验收流程修改；共享规范中的webhook不复制进客户端/公开源码。

## 历史
本次整理前入口逐字保留于[历史快照](doc/history/agents-20261026/root-skill-before068.md)，更早历史从该文件进入。旧设备/旧账号的安装说明不充当本设备当前事实。
