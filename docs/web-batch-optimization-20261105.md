# 网页两弹批处理回归

原creator/publisher skill内增加可重复的批处理脚本，不另建技能包，不复制引擎算法。

613/614首次实测总计18分42秒；媒体上传实际30.37秒，而从开始上传到最终核验280.72秒。首次接口适配、桥接直接等待Promise超时、逐步Agent编排、头像裁切及含义标点返工是主要浪费。

已固化：浏览器异步启动后短轮询、后台标签焦点模拟、4并发媒体上传、当前SDK契约、创建/保存/提审意向宿主原子落盘ACK、32张原始MD5和含义顺序/五项配套图校验、每弹仅提交一次、精确ID和全量同名唯一性回读。标点上传前规整，日志存在时拒绝盲重放。

入口：[creator网页分支](../.openclaw/skills/lyzbcy-sticker-creator/reference/chatgpt-web.md)与[publisher微信分支](../.openclaw/skills/lyzbcy-sticker-publisher/reference/wechat-web.md)。执行begin → 一次合并审图 → assets → 当前SHA素材复核 → publish。中间两道为Agent视觉复核，不额外向用户索要已授权的发布许可。

615/616真实新投稿：各16张原文件MD5、词义及顺序、五项配套ID吻合，各提审一次，同名唯一，最终均Status2待审核。单弹发送9.21/9.42秒；生图首次加载观测111.37/97.62秒；切图去底2.33/2.22秒；SDK上传至两弹最终核验28.97秒。生图观测包含轮询间隔，非精确模型推理时长。

**全过程14分1秒，未达到约5分钟。** 从合并审图到投稿前仍存在多轮头像返工及用户纠正，全部保留在运行计时，没有扣除。不能用29秒接口阶段宣称全流程达标。本轮过程中修正了头像脚本，初始提交9d08ea7并非所有步骤的最终代码；运行快照另记source hashes。

头像按用户最新要求：从当弹16张成品选图做自然方形近景，保留完整头部、肩臂和上半身，不沿发丝/下巴精细抠切，不制造悬空头，不复用base或其他弹头像。仅清理独立文案与装饰；选图有遮挡/残字则更换当弹候选，不重新生头像。原polygon参数只兼容为矩形范围，推荐head_rect。审阅用portrait_reviewed，不将含上半身的图虚写为head_only。

613/614同时按原ID修正了自然上半身头像，16张平台表情身份及其余三张配套素材保持，再提审回读待审核。未对609—612做本轮改动。

本机证据：outputs/web-optimization-1793867969242/trial的events.jsonl、sdk-journal.json、timings.json、report.md、receipts.json及runtime-source-hashes.json。旧单修复在上级目录natural-repair-final-receipts.json。各弹素材目录也保存标准production_record.json、生产日志和微信投递回执。公开源码不包含账号、Cookie、请求头或完整私人响应。

仅新增/修改skill辅助脚本与文档，客户端和冻结引擎仍为已发布0.6.13，本轮不重打同版本安装包。待审核不是审核通过或已上架。
