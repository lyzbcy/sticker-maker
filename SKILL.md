---
name: sticker-maker-dev
description: 表情包一键制作的软件开发、排障、测试与分发入口。
---
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
- 版本位置：desktop/package.json、package-lock.json、sticker_engine/pyproject.toml、cli.py。
- 文档checkpoint：2026-10-14/context-v2。源码、安装记录与实时运行状态分别以[当前状态](docs/current-state.md)为准；不在入口重复维护版本快照。
## 历史与维护
每轮完成后更新当前状态及任务清单，详细输出留在verification；不把同一长日志追加到多个入口。
本次整理前原入口已逐字保留于[历史目录](doc/history/context-checkpoint-20261014/root-skill.md)。
