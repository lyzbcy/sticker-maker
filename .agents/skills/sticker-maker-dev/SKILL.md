## 2026-10-26 · 0.6.6 正式发行
源码/公开版0.6.6，当前开发设备Windows已静默升级并保留设置；按用户要求保持关闭，不再弹出Windows或Mac窗口。Windows/Mac ARM64跨版安装、重启、保留与回退通过，详见docs/current-state.md及docs/release-0.6.6.md（本文件在子目录时从项目根解析）。以下为历史记录。

---
name: sticker-maker-dev
description: 开发、维护或排障表情包一键制作（Electron/Vue/Python）项目时使用，按需读取项目doc与真实验收证据。
---

## 2026-10-26 · 0.6.5 数据看板按需加载与原图分析
- 源码/Windows本机0.6.5，公开正式版仍0.6.2；本轮未公开发版。
- 单图IPC每次20条，整套排名每页20套；原图懒加载与点击放大、搜索、正反排序、发送占比与零发送分析。避免切入看板再次读取已有作品/收益。
- 真实7753条返回20条、20张原图；平台字节不同时只展示当前作品完全同含义的本地原图并标注，不伪称MD5匹配。缺图/破图明确显示。
- 后端770通过/6跳过，前端146通过；冻结4模块语义与源码一致，真实冻结CLI返回20条。原42831份保护素材/评分/元数据SHA保持。
- 本机NSIS升级exit0，实际安装载荷与候选一致、开始菜单入口原路径；可见UI确认20行、原图放大、下一页、搜索、零发送排序及冷重启；详见[本轮](../../../docs/analytics-lazy-20261026.md)及归档VERIFICATION。
- 源码/安装回滚分别在另一副本验证；实际源码和安装保留0.6.5。未自动抓取平台、投稿、改作品或评分。

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
文档checkpoint：2026-10-23/standards-v1；文档请求不启动生成、投稿、安装或历史任务续接。
本轮结果更新docs/current-state.md；未完成事项更新docs/roadmap.md；详细命令、哈希、截图与回执留verification。
只在流程/字段变化时更新对应专题。入口放摘要和链接，不重复追加长日志。
每轮写回五项：已验证结果、证据路径、源码/安装/运行状态、未完成事项、下一步前置核验。区分预览、真实修复、投稿及身份核验；已有成功/未知结果先查回执。
历史开发skill原文完整保留于[归档](../../../doc/history/context-checkpoint-20261014/development-skill.md)。
