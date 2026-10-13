> 现状：验收中（未正式发布）
> 负责人：捞鱼工作室 / Codex
> 最后更新时间：2026-10-13

# 软件开发规范逐项审计（0.5.1 候选）

## 结论
原0.5.0未满足全部要求。当前已完成代码修复与本机样品验收，但“可正式分发给粉丝”仍待干净机器安装/升级、Mac端与公开反馈接收服务验收。不得将单测、源码或进程存在当作正式安装/更新通过。

|规范来源（reference/standards）|当前实现与证据|状态|
|---|---|---|
|软件对应开发 skill.md|根 SKILL、docs/agent 导航、roadmap/tech/audit/distribution/updater；三处源码版本0.5.1|已补齐；远端发布待验收|
|日志系统.md|JSON-lines 阶段心跳、可展开复制日志、实际错误透传|本机+单测通过|
|用户提意见&反馈.md|显著反馈入口、分类/留言、可选脱敏日志预览、失败保留草稿、15s超时、30s防重复|UI/协议mock通过；公开接收接口待配置；不把机器人密钥放进公开包|
|自适应更新检测.md|Asia/Shanghai每日尝试/成功分记、SemVer正式版本、固定受信URL+强制SHA、流式进度、下载失败保留、ready/commit/abort、安装备份恢复|单测+真实PowerShell交接通过；真实安装升级重启未通过验收|
|个人推广页.MD|作者页、既有三个推广二维码、软件介绍页入口|沿用既有素材；尚待装机最终视觉复核|
|不打扰用户的求好评.md|原15天延迟/持续生效逻辑；问题入口走直接反馈|代码+UI回归通过|
|图标logo.md|沿用本软件原创图标；全局software-logos.json登记；reference/icon-selection.json哈希|已登记（非重新随机抽取）|
|美化设计.md|cream/forest主题、隐藏白色系统标题栏、WPF主题安装器、非系统盘优先、中文换目录、自选快捷方式|安装器预览和真实解包版窗口通过；真实安装待CI|
|润物细无声.md|既有精选角色/原创贴图资源与FeaturedShowcase|沿用；实际新图样品可视检查通过|
|ios与win兼容架构.md|Mac/Windows依赖隔离；统一协议；Windows native Codex无需Node；打包Chromium+keyring；Mac分发脚本原子替换并校验|Windows冻结运行真实通过；Mac待CI；不宣称支持iPhone|
|强制刷新组件.md|稳定version.json来源、文本安全渲染、离线介绍可见、手动版本刷新、自动刷新防循环|源码修复；公网仍0.5.0，未提前指向不存在包|
|网页回归测试.md|按规范授权独立ux_regression子代理；真实Vite浏览器+解包Electron；16个前端文件85项测试|通过，报告verification/ux-regression.md|
|启动器适配/接入指南及适配规范|现有登记/图标/真实exe识别规则已在软件中心；最终包登记描述与实际装机识别需一致|待最终发布、主维护启动器接入及严格脚本+真实安装验收|
|skill 静默更新.md|本地规范快照；项目渐进式入口已补齐；版本与实际产物区分|文档已补；远端备份待执行|

## 重要真实缺陷
- 生图调用失败却扫描全部历史图片，误报成功：现仅允许本次thread_id、请求起始mtime之后的新图，reader全部join后再读取输出；无本次身份不使用全局最新图。
- Native安装缺code-mode-host导致实际生图失败：改为四组件SHA校验、完整资产预检查、同release staging整体切换，任一组件失败保留整套旧版；manifest逐文件检测。
- 批量默认自动提交：改为默认1组、不自动投稿，导出ZIP独立于微信创作者账号。
- 保存失败误显示概率之和错误：真实异常透传、保存失败不进入下一步。
- 版本和测试污染：软件/CLI/pyproject统一0.5.1；隔离测试数据，修复Windows UTF8与平台fixture。

## 已观察证据
- 基线：桌面65通过；引擎17失败/457通过/3跳过（verification/baseline-*.txt）。
- 修复：桌面85通过；引擎506通过/6跳过（verification/modified-*.txt）。跳过限POSIX shell/symlink/需授权fixture，不是假装生产能力通过。
- Windows冻结引擎：PATH仅System32、隔离HOME、没有开发Python/Node情况下真实启动Chromium和keyring（verification/frozen-runtime-*）；最新打包仍需重复该验收。
- 真实单次4x4生图：episode_20261013_171309，16表情；21张素材ZIP导出；原图和240px透明成品已查看；没有执行微信提交。
- 早期假成功记录generation-false-success.txt保留但作废，绝不计入验收。
- 事务证据verification/transaction：基线错误选历史图、修复返回None、另一副本回滚恢复原hash/行为，实际源代码保持修复。

## 发布门禁
1. 干净Windows：真实安装、目录选择、卸载登记版本、无需开发依赖运行、窗口可见；从旧版升级，校验作品和设置保留，失败恢复。
2. Mac arm64：真实签名校验、安装、引擎/浏览器启动与更新；普通Mac的Gatekeeper提示与操作步骤仍需确认。
3. 配置公开反馈转发服务并做明确标记的测试留言；企微群机器人密钥仅服务端持有。
4. 严格启动器适配验收；最终发布包SHA+官网元数据+下载文件公网回读一致。
5. 先过门禁，再不可变发布0.5.1；候选包不是粉丝正式版，网站继续保留0.5.0。
