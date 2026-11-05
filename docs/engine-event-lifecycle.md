现状：0.6.9源码/本机已交付，192前端通过；设置不误保存、资源只读刷新结束回就绪、可见版本/冷重开/保护数据通过。历史0.6.8反例保留。
负责人：本聊天
最后更新时间：2026-10-26

# 引擎事件与反馈交互
runtimeEvents.js负责5类IPC订阅、销毁门和退出/重启瞬态复位；engine.js保留原业务命令。Pinia scope销毁会释放监听，已排队晚回调不再写入store。preload每个订阅返回独立、幂等解绑函数。
activityIsHistorical区分已结束任务历史与新活动；并发任务优先展示，结束后回到就绪但保留60条活动历史。原生成成果/错误和更新进度优先级保留，不为此修改更新器决策。
反馈复制与发送使用相同日志勾选；复制等待中单飞，失败保留草稿/提示/可重试，不自动发送反馈。日志默认仍勾选且脱敏预览。

## 验证与边界
隔离原154通过，新增19基线6通过/13失败、候选19通过；全173通过及Vite构建。副本回滚4原文件/4新增文件后154通过。集成后结果、成包与本机实装以本轮归档回执为准，不能用本段mock结果冒充真实安装。
测试文件：desktop/tests/runtimeLifecycle.test.js、preloadLifecycle.test.js、feedbackLifecycle.test.js。不发送平台请求、不生图、不重投、不修改作品、评分和未知回执。
本轮归档：E:/共享/创业/09-归档/agents任务执行-20261026/sticker-dev068；原隔离候选：同目录上级sticker-runtime-lifecycle。

## 真实安装发现的剩余路径
2026-10-26本机0.6.8，设置页初始化会调用save_prefs；诊断日志确认req-19在14.2秒完成，但主进程的tracked列表不包括save_prefs，python-progress没有对应task-status结束通知，底栏仍是881/881。19项mock只覆盖tracked事件，不能代表此路径修复。
资源页在保存进行时拿到busy错误；后续quiet library_status成功恢复库信息，却不清旧busy提示。下一批应按请求生命周期跟踪所有有进度的命令（非定时器猜结束），区分临时读取错误与其他操作错误；同时避免设置初始化无操作就写prefs。不得为清提示重放业务、绑定账号或改平台状态。
实际安装1255载荷匹配，显示0.6.8并从原开始菜单冷重开；当前安装保留0.6.8，公开0.6.6不变。剩余问题保留原生失败证据，不以组件绿灯勾掉实际门槛。

## 0.6.9 实际请求生命周期
主进程commandRunner集中拥有每个bridge请求的task id、开始、进度、finally结束。已知长命令（含save_prefs）立即宣布开始；未列名命令首次产生进度时提升为任务，无进度的library_status轮询保持安静。成功/失败都结束同一个id，已结束请求的晚进度丢弃，不按秒数猜完成，不重放业务。
设置页onMounted读取偏好，等Vue nextTick完成初始化watch flush后才开放用户改动保存；开页本身不保存、不标准化原值。保存返回false或抛异常不显示成功，卸载清理提示定时器并忽略晚回执。
资源库只记录自己产生的状态读取错误；quiet成功可清该错误，其他操作错误改变后失去该所有权，不清导出/绑定等错误。quiet失败仍不覆盖用户操作错误。
新增19条测试在68基线7通过/12失败，69候选19通过；原173项均通过，总192通过。commandRunner.test.js执行index.js实际python-command注册块，不以手工task事件代替适配层。settingsHydration.test.js挂载真实SettingsPanel，resourceStatusRecovery.test.js覆盖错误归属。
构建、实际启动/冷重开、原生设置页不误保存及底栏归位、保护文件SHA以归档sticker-dev069/VERIFICATION.txt为准；未验项目不提前勾选。公开正式0.6.6未变。
