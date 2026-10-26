## 2026-10-26 · 0.6.6 正式发行
源码/公开版0.6.6，当前开发设备Windows已静默升级并保留设置；按用户要求保持关闭，不再弹出Windows或Mac窗口。Windows/Mac ARM64跨版安装、重启、保留与回退通过，详见docs/current-state.md及docs/release-0.6.6.md（本文件在子目录时从项目根解析）。以下为历史记录。

---
name: sticker-maker-dev
description: 表情包一键制作的软件开发、排障、测试与分发入口。
---

## 2026-10-26 · 0.6.5 数据看板按需加载与原图分析
- 源码/Windows本机0.6.5，公开正式版仍0.6.2；本轮未公开发版。
- 单图IPC每次20条，整套排名每页20套；原图懒加载与点击放大、搜索、正反排序、发送占比与零发送分析。避免切入看板再次读取已有作品/收益。
- 真实7753条返回20条、20张原图；平台字节不同时只展示当前作品完全同含义的本地原图并标注，不伪称MD5匹配。缺图/破图明确显示。
- 后端770通过/6跳过，前端146通过；冻结4模块语义与源码一致，真实冻结CLI返回20条。原42831份保护素材/评分/元数据SHA保持。
- 本机NSIS升级exit0，实际安装载荷与候选一致、开始菜单入口原路径；可见UI确认20行、原图放大、下一页、搜索、零发送排序及冷重启；详见[本轮](docs/analytics-lazy-20261026.md)及归档VERIFICATION。
- 源码/安装回滚分别在另一副本验证；实际源码和安装保留0.6.5。未自动抓取平台、投稿、改作品或评分。

## 当前开发（2026-10-26）
源码0.6.4：已接单图报告与按日期排名；486套/7753张真实读取通过。Windows本机已升级0.6.4，真实单套刷新1/1成功、分页/冷重启通过，版本以本轮 [记录](docs/single-metrics-20261026.md) 为准。未公开本版。

## 上次交付（2026-10-26）
源码与Windows本机 **0.6.3**；收益实际刷新20→270且冷重启保持，看板/精品重制方案入口已接入。未公开发布；详情以[当前状态](docs/current-state.md)和[本轮](docs/task-20261026.md)为准。下方0.6.2维护描述为历史。


<!-- release-cadence-local-upgrade-20261024 -->
## 后续发版与本机交付（2026-10-24）

遵循[共享目录最新约定](../../AGENTS.md#软件发版频率与本机升级用户约定2026-10-24)：普通更新累计约 2～3 个开发版本再公开发版；大更新或用户明确要求时提前发行。每次功能更新后，本机必须升级到最新开发版，并核对实际运行路径、版本及日常启动入口，保留用户数据和回退；优先本机构建/缓存，源码或隔离测试通过不能算本机升级完成。源码、本机、公开版本分别记录；文档/网站/统计工程按实际类型交付。此约定替代历史逐次发版或不替换本机安装的默认限制，私有工具仍不公开。

## 2026-10-24 本轮维护

当前源码/维护：**0.6.2（仅文档checkpoint）**。四处版本与实际字段复核；补日志模块文档元信息、历史导航；现有批写、排障及每日更新链路保持。

本轮未改应用行为；后续功能开发仍需引擎/桌面/安装升级回归，不把文档核对算业务测试。

计划、验证与回退：[维护记录](docs/maintenance-20261024.md)。下方2026-10-23暂停记录及旧候选描述为历史；本次不把源码修改称为正式发行。

# 表情包一键制作
## 项目与技术栈
给粉丝制作自己的表情包；生成、视觉质检、微信投稿、平台身份核验是不同完成状态。
Electron 30 / Vue 3 / Pinia / Python 3.12 / PyInstaller；Windows x64、macOS ARM64。
## 读取入口
- [开发导航](docs/agent.md)：先选本次任务相关文档。
- [当前状态](docs/current-state.md)：唯一当前进度快照，包含证据入口与未完成项。
- [长任务续接](docs/long-task-handoff.md)：上下文切换或继续历史任务时按需读取。
- [开发 skill](.agents/skills/sticker-maker-dev/SKILL.md)：开发纪律及模块路由。
## 目录地图
- desktop/src：主进程、预加载、Vue界面；desktop/site：网站与公网更新清单。
- sticker_engine：JSON-lines引擎、后端测试；scripts：已存在的安装版操作驱动。
- docs：当前状态和维护文档；doc/reference：模块细节；doc/history：只读历史。
- reference/standards：项目自包含规范；verification：原始哈希、回执、回归及回滚证据。
## 开发约定
- 保留已有未提交修改和真实作品数据；按模块读文档，不全量加载历史记录。
- 程序改动同步代码、相关文档和应用/Python版本；正式产物验证后才更新公网清单。
- 仅文档整理记录文档checkpoint版本，不制造新应用版本或安装包。
- 新包先校验再安装；结果按真实版本、SHA及回执判定，不以源码版本冒充实装。
## 关键不变量
- 角色身份门禁、账号检查、资源库锁、投稿完整性和结果未知核销机制保持有效。
- “提交成功”与新鲜平台身份核验分别记录；已成功或结果未知的投稿不盲目重试。
- 评分保持真实来源；缺失人工/AI评分为null，不用视觉质检分替代。
## 测试与版本
- 后端：sticker_engine/.venv/Scripts/python.exe -m pytest tests -q --ignore=tests/agent（在sticker_engine目录）。
- 桌面：npm.cmd test（在desktop目录）。完整测试说明见[开发不变量](doc/reference/development-invariants.md)。
- 版本位置：desktop/package.json::version、desktop/package-lock.json::version/packages[""].version、sticker_engine/pyproject.toml::project.version、sticker_engine/sticker_engine/cli.py 的版本返回值。
- 文档checkpoint：2026-10-23/standards-v1。源码、安装记录与实时运行状态分别以[当前状态](docs/current-state.md)为准；不在入口重复维护版本快照。
## 历史与维护
每轮完成后更新当前状态及任务清单，详细输出留在verification；不把同一长日志追加到多个入口。
本次整理前原入口已逐字保留于[历史目录](doc/history/context-checkpoint-20261014/root-skill.md)。

<!-- standards-todo-20261023:start -->
## 2026-10-23 规范待办（先记录，暂停整改）

- 待办与逐项验收要求：[docs/standards-todo-20261023.md](docs/standards-todo-20261023.md)。
- 此前已有候选改动回填；仍按条目复核，未宣称完整验收或发布。
- 本次仅更新开发记录；后续开发先逐项核对，勿重复套用未验收实验副本。
<!-- standards-todo-20261023:end -->
