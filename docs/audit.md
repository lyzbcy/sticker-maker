> 现状：0.5.1正式发行，分发验收完成
> 负责人：捞鱼工作室 / Codex
> 最后更新时间：2026-10-13

# 软件开发规范逐项审计

## 结论
原0.5.0存在未完成要求及真实缺陷。本轮补齐开发入口、易用性、安装运行、反馈、更新和适配；0.5.1已正式发布。按每类证据分别记录，不用单测或历史图片冒充真实生成/安装。

|规范来源（reference/standards）|实现与证据|状态|
|---|---|---|
|软件对应开发skill.md|根SKILL、docs导航及模块文档、规范自包含；desktop/lock/pyproject/CLI0.5.1|代码/文档/版本同步，main远端备份|
|日志系统.md|JSON-lines阶段心跳、错误透传、底部日志展开/复制；运行时错误可见|单测+实际桌面窗口|
|用户提意见&反馈.md|显著入口、分类留言、可取消日志、脱敏预览、草稿保留；公开私密转发、持久ID、防重复回执、55s超时|519测试中的7项转发；实际UI→公网→企微ACK0；同IDduplicate=true|
|自适应更新检测.md|上海日期每日首启；稳定semver、固定来源+强制SHA；下载进度/互斥；Win握手、备份、版本核验、可见重启；Macstage/签名/旧bundle备份|Win真实0.5.0→0.5.1升级与作品保留；Mac真实替换/坏签名保留；失败类型见下方|
|个人推广页.MD|作者介绍、3个既有二维码、软件介绍页与视频|沿用既有素材，前端回归|
|不打扰用户的求好评.md|15天延迟逻辑，问题引导直接反馈|代码+独立UI回归|
|图标logo.md|本软件原创图标，全球software-logos.json登记及reference/icon-selection.json SHA|原图与哈希登记一致|
|美化设计.md|cream/forest主题；无白色系统标题栏；WPF主题安装器；非系统盘优先；中文换目录；快捷方式/完成打开可选|Win真实主题安装登记/窗口截图通过|
|润物细无声.md|精选角色与原创贴图；默认先1组且不自动投稿|16张真实新图+21素材ZIP视觉查看|
|ios与win兼容架构.md|桌面Win x64/Mac ARM64依赖隔离；内置Chromium/keyring；统一协议；Native Codex四组件原子校验|Win/Mac安装目录实际冻结运行时与窗口通过|
|强制刷新组件.md|固定version.json、安全文本渲染、离线介绍、手动刷新、防循环；Pages dispatch明确读取live main|官网公网0.5.1回读；双平台发布SHA一致|
|网页回归测试.md|规范授权独立ux_regression；真实Vite/解包Electron；86项桌面单测；680px首屏反馈回执可见|独立回归与实际窗口分别验收|
|启动器适配/接入指南及适配规范|产品ID/主exe/卸载名/原图/视频；最终包元数据；主维护Win目录登记；私有Win/Mac分支产品元数据备份|35项严格脚本exit0，真实自动识别既有安装；独立隔离UI生产shell.openPath打开0.5.1原生可见；新包安装/更新另由干净CI验证|
|skill静默更新.md|规范快照、渐进式入口、源码main备份、真实版本区分|已补齐|

## 真实修复
- 生图工具失败却选取历史图片：仅本次thread_id与请求开始后的新图片；reader join后取输出；无身份不回退全局最新图。
- 缺code-mode-host造成实际生成失败：完整四组件同release/SHA/staging/manifest；损坏或version/login失败正确进入修复或登录。
- 默认批量自动投稿：改为1组、不自动投稿；本地ZIP独立于微信账号。
- 保存失败显示错信息、白页、初始化故障无提示：异常透传，Vite模块正确导出，失败可见。
- 原NSIS卸载名称附版本与登记位置造成安装器假失败：稳定展示名，兼容旧名称，按DisplayIcon实际目录核验。
- Mac浏览器framework被PyInstaller重签破坏：COLLECT后完整复制symlink并签名核验。
- 反馈成功提示被状态栏遮挡：放首屏，实际680px视口可见，loopback布局测试不发送真实消息。

## 核心证据
- 基线：桌面65通过；引擎17失败/457通过/3跳过。
- 当前：桌面86通过；后端/转发519通过、6平台跳过（POSIX/symlink等既有fixture）。
- 真实生成：episode_20261013_171309，16张透明240px新图；21素材ZIP；对应本次会话与mtime；微信平台实际提交0条。历史假成功记录作废并保留。
- QA38386084597、38387951697：Win/Mac全绿；Windows主题安装登记、冻结浏览器/凭据后端、实际可见窗口；旧正式0.5.0经新助手实际升级、confirmUpdateRestart及作品sentinel保留。
- Mac旧0.5.0实际bundle替换；原hash备份；破坏签名后安装器exit1，既有bundle/作品保留。窗口由独立实际启动验证；换包测试headless。
- Windows失败恢复证据为源码/fixture；Mac坏签名拒绝为实际安装器。旧0.5.0需要手工迁移一次，不能说旧助手被远端修复。
- 原nginx配置真实回滚校验SHA后重应用，analytics保持健康；最终反馈服务active；密钥仅服务端0600文件；1条明确标记的验收留言，无用户日志。
- 发布run38389217935成功，正式产物重新构建；最终字节校验见verification/final-release/release-verification.json，不沿用候选包SHA。

## 分发状态
入口https://lyzbcy.github.io/sticker-maker/；GitHub正式v0.5.1。Windows约444MB、Mac约499MB；粉丝无需Python/Node，但使用自己的ChatGPT登录、网络与生图额度。系统签名：Windows未代码签名，Macad-hoc未Apple公证；首次系统确认步骤见fan-guide.md及Apple官方指南。不同电脑网络/系统设置仍有差异。

事务四件套见verification/transaction和feedback-deployment；原始397文件备份只保存在本机。现有个人作品、账号和运行中的安装版保持原状，验收均用隔离数据。软件中心仅更新此产品目录数据，Windows0.8.10/Mac0.9.4客户端版本保持。

最终公开下载：Win443765034字节，SHA fafb405c130c47bc7dd9d2282978744e699937ce362ab838e3f9d42a74a7ba2d；Mac499356699字节，SHA af7d89ee2024b4199a2713f15de272683e7a1d049b393d8e032559adcef8a908。完整下载字节/官网/GitHubdigest一致，Mac全ZIP CRC与外层bundle0.5.1通过。启动器UI采用未修改官方0.8.10resources+Electron30 dev host，隔离关联与正常公网latest预检明示；首轮协议登记已恢复既有正式0.8.6处理器，个人软件4个原进程均保留。
