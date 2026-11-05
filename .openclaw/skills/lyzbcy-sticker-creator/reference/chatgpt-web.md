# ChatGPT网页制作：原Sticker Maker分支

只更新本仓库的现有creator/publisher skill和引擎，不安装独立网页包，不复制第二套素材/算法。概率与服装只读本skill config.yaml；单人85%、双人15%，单人条件星星布丁75%、捞鱼25%，双人为二者。

## 第一格固定方框头像

首次生图即约定第1格为正面头肩胸像，可独立发送；完整头发、脸与自然肩臂放在顶部居中80%方框内，文案只在底部92%—99%字幕带。双人时第一格两人并肩近景。其余15格只限定主题、场景、人群，让模型发挥，不强制故事。普通贴纸保留白描边。

头像始终取原始整图的第一格，坐标不按人物收紧、不重新居中：side=round(min(w,h)*0.8)，x=(w-side)//2，y=0。仅沿既有流程去洋红，再按方框裁剪和等比缩放；不抠字、不删白边、不做轮廓mask/连通域清理、不选其他格、不二次启发式裁头。240封面同图缩50图标。当前裁剪函数和像素保持测试在scripts/web_head_crop.py与test_web_head_crop.py。

如果生成未遵守预留区，记录失败，不暗改坐标、换格或擦字冒充成功。617/618首次中心80%仍带字幕，两弹已统一改为顶部居中80%；这是固定规则的全局修订，详见 [实测](../../../../docs/first-panel-avatar-20261105.md)。

## 执行三个阶段

1. node scripts/web_batch.cjs begin --config <config.json>

config含outputRoot、assetsRoot、logDir、accountAnchor和两项themes（theme/scenario/audience）。从查号前开始计时。脚本读取本人后台完整List（含草稿待审）及已知账号作品ID，确定最大编号后用web_prepare.py抽样、复制实际base并记SHA。已有同名目录或未知结果先续接核验，不能覆盖/重生。微信标签关闭时自动打开官方入口，登录失效则停在登录状态，不导出Cookie。

通过ChatGPT真实附件输入上传base，确认加载后发送；两弹分别新对话并行等待图像。首次响应同时要求16项index/text/meaning JSON，只作为候选，不能当图片真值。下载本次生成原图，保存聊天URL与SHA；脚本调用当前引擎切图/去底，自动生成首格头像和五项本弹配套图，输出review-all.jpg。网页操作和生成细节见 [质量规范](chatgpt-web-quality.md)。

2. Agent在同一张review-all.jpg核对32格身份、文字、切图边缘及两套五项配套图，写review.json：albums内每项只有episode、16个meanings、description，不再填head_index/head_rect/polygon/caption_regions。然后执行 node scripts/web_batch.cjs assets --manifest <manifest.json> --review <review.json>。

此阶段规整词义标点（啊？→啊）、检测重复并更名，更新头像与素材来源路径；已审素材字节保持不变，无额外头像选图识图。发现实际质量问题仍需处理并计时，不能拿脚本尺寸检查冒充视觉合格。

3. 将当前发布素材清单SHA写入approval.json：逐弹episode、approved、portrait_reviewed、asset_hashes，human_score=null。node scripts/web_batch.cjs publish --manifest <manifest.json> --approval <approval.json>。

发布使用原 [publisher SDK分支](../../lyzbcy-sticker-publisher/reference/wechat-web.md)：4并发上传、创建/保存/提审前宿主原子日志ACK、32张原始MD5/词义/顺序及五项配套ID校验、每弹仅提交一次，最后按精确ID及全量同名唯一性回读。sdk-journal.json存在时拒绝重放，超时/未知先核销。不可把上传、保存、待审核当审核通过或上架。

## 来源与计时

后处理、赞赏图和横幅继续调用同仓库当前引擎及现有脚本，禁止携带复制快照；本弹配套图每弹本地重渲染，不复用共享赞赏页。头像必须来自当弹第一格，不能复用base或其他弹。

全程从首次启动到最终回读，保留登录恢复、失败、补救、审阅和Agent编排等待。另报连续生产用时可以，但不得替代总时长。617/618完整6分31秒；含首次入口失败与补救93秒，恢复后生产4分58秒，SDK29秒。首次头像参数全局修订及一次额外方框验证也在日志内；不保证外部生图耗时。
