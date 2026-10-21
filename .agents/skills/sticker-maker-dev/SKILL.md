---
name: sticker-maker-dev
description: 开发、维护或排障表情包一键制作（Electron/Vue/Python）项目时使用，按需读取项目doc与真实验收证据。
---
# 表情包一键制作 · 开发 Skill
## 冷启动
项目根目录由本文件向上三级定位。先读根[SKILL.md](../../../SKILL.md)、[docs/agent.md](../../../docs/agent.md)与[当前状态](../../../docs/current-state.md)。
当前请求为文档整理时只改文档；历史交接与旧目标不自动扩展本轮操作。
继续长任务或上下文换代时按需读[续接说明](../../../docs/long-task-handoff.md)，不重载全部历史聊天。
## 按需读取
- 生图/彩底/切图/文字/封面：[pipeline](../../../doc/reference/pipeline.md)。
- 微信平台自动化：[publish](../../../doc/reference/publish.md)与续接说明中的成功/未知状态判据。
- 资源库/冲突/迁移：[resource-library](../../../doc/reference/resource-library.md)。
- 系列编号：[series](../../../doc/reference/series.md)。
- 发布包/更新：[distribution](../../../docs/distribution.md)、[updater](../../../docs/updater.md)。
- 锁、缓存、测试隔离或历史事故：[开发不变量](../../../doc/reference/development-invariants.md)。
## 核心纪律
- 保留既有未提交修改、作品、评分和凭据；真实素材/身份分歧由证据驱动处理。
- 实际provider输入与归档prompt保持一致；角色身份门禁保持有效。
- 投稿用软件流程与完整性门禁；UI提交成功不等于平台ID已经绑定，未知结果先查证再核销。
- 已投稿或结果未知的回执用于续接同一任务，不重新提交；暂时上传接收数不计为投稿数。
- 程序改动同步代码、文档、版本并测试；文档整理独立记录checkpoint，不制造安装包版本。
## 状态写回
文档checkpoint：2026-10-14/context-v2；文档请求不启动生成、投稿、安装或历史任务续接。
本轮结果更新docs/current-state.md；未完成事项更新docs/roadmap.md；详细命令、哈希、截图与回执留verification。
只在流程/字段变化时更新对应专题。入口放摘要和链接，不重复追加长日志。
每轮写回五项：已验证结果、证据路径、源码/安装/运行状态、未完成事项、下一步前置核验。区分预览、真实修复、投稿及身份核验；已有成功/未知结果先查回执。
历史开发skill原文完整保留于[归档](../../../doc/history/context-checkpoint-20261014/development-skill.md)。
