> 现状：已部署并通过真实反馈与回滚验收
> 负责人：捞鱼工作室 / Codex
> 最后更新时间：2026-10-13

# 反馈转发服务

用户已选择使用现有服务部署。已确认文档中的腾讯云服务器和现有HTTPS 8443入口，保留443 DERP、launcher-stats及其它应用。文档专用SSH密钥id_ed25519_tencent在本机缺失；现有默认密钥登录返回Permission denied。目前没有远端写入或上线成功记录。

源码server/feedback_relay.py、systemd与nginx-location.conf已准备。绑定127.0.0.1:18774；仅新路由/sticker-maker-feedback；机器人URL只在服务器/etc/sticker-feedback.env，权限0600。客户端feedback-config.json仅放公开HTTPS转发URL，不含密钥。

服务仅允许本产品文本反馈；12KB输入、8并发上限、10s读超时、每IP30s一次、总3批/分钟；不接受用户提供目标URL；服务端再次脱敏。长文本按UTF8边界分为1700字节片段，保留完整留言与诊断内容。只有所有片段的业务errcode=0才返回送达；部分送达/超时均不是成功。

SQLite最多约8MB，回执保存24小时，不保存IP/留言/日志原文；重复request_id只读既有结果，不重发；相同ID内容变化拒绝。客户端在用户数据目录先存ID/摘要再发请求，丢回执后同一内容使用同一个ID；回执未确认时不换ID提交不同内容。草稿仍保留，可复制诊断信息联系作者。

## 部署顺序与回滚

1. 取得该现有服务的可用SSH密钥路径，先只读检查df、现有nginx配置和8443证书/health，不覆盖其它服务。
2. 为本服务保存原文件哈希与副本，上传源码到/opt/sticker-feedback/releases/版本，新环境文件0600；环境内容从本机规范读取，不打印、入Git或装进客户端。
3. 启动独立systemd，回环health与无效请求验证；在现有8443 server block中只插入本location include。nginx -t成功后reload；失败恢复原配置、停止本服务，不动其它服务。
4. 用真实公网TLS验证health/无效请求；发送一次明确标记的验收留言（模拟日志，不传真实作品/账号），验证errcode=0和同ID重复不发送。只有通过后写客户端公开URL并重新打包。
5. 上线失败恢复原nginx配置与旧current指针、旧systemd；保留回执数据库，防重复送达。现有launcher-stats/health必须前后都正常。

当前仅本机单元与真实回环HTTP测试（上游mock），未发真实企业微信消息。公开URL为空是有意发布门禁，不宣称粉丝反馈已可送达。

2026-10-13：回环真实HTTP+上游mock 7项通过；默认SSH密钥root登录未通过；公网8443/launcher-stats/health请求超时，无服务端写入。需要用户提供已授权服务的专用密钥文件路径继续实际部署。

## 真实上线结果

现役ubuntu账号使用本机默认密钥连接成功并具有sudo权限，无需新增/粘贴凭据。服务已部署到现有服务器127.0.0.1:18774，经8443新路由公开TLS；主配置仅新增一个include。实际回滚恢复原nginx SHA256（1537733f…1ca34）与停止本服务，原analytics健康始终正常；随后重新启用转发，最终服务为active。

公开health与原analytics均200；实际解包桌面UI发送一条标明验收的模拟留言，取消日志，无用户数据。企微业务errcode=0，UI“已送达作者”并清空草稿；同ID第二次请求duplicate=true仅查询回执。证据verification/feedback-deployment/VERIFICATION.txt与feedback-live/result.json。客户端已配置只有公开HTTPS URL的feedback-config.json，不含机器人密钥。

维护：现有短期证书续期timer保持不动；监听服务有8并发上限与资源配额；反馈接收与自动更新/生图账单无关。新包需重新构建及清洁机器验收。
