> 现状：当前开发导航；版本与运行状态只在current-state.md维护
> 负责人：捞鱼工作室 / Codex
> 最后更新：2026-10-14；文档checkpoint 2026-10-14/context-v2

# 开发导航
先读[current-state.md](current-state.md)，只加载与当前请求相关的下列模块。
上下文切换时再读[long-task-handoff.md](long-task-handoff.md)，历史记录不作为默认入口。

|任务|按需文档|
|---|---|
|任务排期、下一步|[roadmap.md](roadmap.md)|
|架构与依赖|[tech.md](tech.md)|
|GIF一键制作、一次生图多帧、离线合成原型|[gif-one-shot.md](gif-one-shot.md)（2026-10-19实验checkpoint，尚未接入正式软件）|
|开发不变量、测试隔离、缓存/锁的历史坑|[development-invariants.md](../doc/reference/development-invariants.md)|
|彩底生图、分格、白衣保留、底字、无字封面|[pipeline.md](../doc/reference/pipeline.md)|
|微信投稿、完整性、名称、未知结果核销|[publish.md](../doc/reference/publish.md)、[续接操作](long-task-handoff.md)|
|规范工程、专辑名目录、旧副本释放、删除原图瘦身|[project-format.md](project-format.md)|
|跨电脑资源库/设置冲突、空目录清理、人工评分|[desktop-issues.md](desktop-issues.md)、[resource-library.md](../doc/reference/resource-library.md)|
|每10弹人工评分表、回填与新候选检查|[human-rating-batches.md](human-rating-batches.md)|
|已被否定虚高的AI历史分/量表追溯|[ai-rating-standard.md](ai-rating-standard.md)|
|平台接口同步、理由与缓存、真实耗时|[sync-performance.md](sync-performance.md)|
|发布安装包、启动器、升级恢复|[distribution.md](distribution.md)、[updater.md](updater.md)|
|粉丝首次使用与自愿教程|[fan-guide.md](fan-guide.md)|
|反馈服务与企微送达|[feedback-service.md](feedback-service.md)|
|日志落盘、排障模式、实时任务与脱敏导出|[logging.md](logging.md)|
|0.6.2双端架构核对、教程退出、标签与安装包瘦身|[处理记录](desktop-usability-20261021.md)|
|完整验收标准|[audit.md](audit.md)|

旧专题目录见[doc/README.md](../doc/README.md)。整理前导航长日志保留于[历史归档](../doc/history/context-checkpoint-20261014/agent.md)。
