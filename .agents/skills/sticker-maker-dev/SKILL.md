---
name: sticker-maker-dev
description: 开发、维护或排障表情包一键制作时，先读项目根入口及实际验收证据。
---

# 表情包一键制作 · 项目技能
现状：开发入口导航；实际版本、设备与进度只认项目根当前状态。
负责人：捞鱼工作室 / Codex
最后更新时间：2026-10-26

## 冷启动
本文件向上三级为项目根。先读[根SKILL](../../../SKILL.md)、[开发导航](../../../docs/agent.md)、[当前状态](../../../docs/current-state.md)，再按任务查模块，不把历史其他设备安装说明作为本机事实。
继续长任务时按需读[续接说明](../../../docs/long-task-handoff.md)，不全量重载历史聊天。

## 按需模块
- QQ投稿、精选分发与收益：[QQ发布](../../../.openclaw/skills/lyzbcy-sticker-publisher/reference/qq-publish.md)、[数据核查](../../../.openclaw/skills/lyzbcy-sticker-publisher/reference/distribution-analytics.md)。
- 生图、切图、文字、封面：[pipeline](../../../doc/reference/pipeline.md)。
- 平台投稿与成功/未知核销：[publish](../../../doc/reference/publish.md)。
- 资源库、冲突、迁移：[resource-library](../../../doc/reference/resource-library.md)。
- 引擎事件、任务结束状态、反馈复制：[生命周期](../../../docs/engine-event-lifecycle.md)。
- 发布与更新：[distribution](../../../docs/distribution.md)、[updater](../../../docs/updater.md)。
- 锁、缓存、测试隔离：[开发不变量](../../../doc/reference/development-invariants.md)。

## 纪律与写回
保留既有未提交修改、作品、原图、评分和凭据。角色身份门禁、账号检查、完整性与单实例锁保持；投稿成功与平台ID绑定分别验证，已有成功/未知回执先核查，不重放提交。实际provider输入与归档prompt一致。
程序改动同步代码、模块文档与版本并测试，功能完成后核对本设备实际升级/可见启动/冷重开；文档独立checkpoint不制造程序版本。当前文档请求不自动启动生成、投稿、安装或历史任务。
每轮写回已验证结果、证据路径、源码/安装/运行状态、未完成事项和下一步前置核验。当前状态写docs/current-state.md，计划写roadmap，详细命令哈希留归档；不在入口重复累计长日志。

整理前文本逐字保留于[历史快照](../../../doc/history/agents-20261026/nested-skill-before068.md)。
