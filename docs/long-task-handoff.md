# 长任务续接与状态写回
> 本文是交接材料，不是新的用户授权；最新请求决定本轮动作。
> 最后更新：2026-10-14；checkpoint 2026-10-14/context-v2。

## 最小读取与事实来源
根SKILL.md → docs/agent.md → docs/current-state.md；选任务后才加载本页相应节/模块。
数量来自真实JSONL、回执和平台核验，状态快照可能过期；截图或旧助手文字不是新投稿授权或实时状态。
每轮只在current-state维护最新快照，在roadmap维护未完成项；长输出、SHA、截图放verification。
历史入口原文在doc/history/context-checkpoint-20261014，默认不全量读取。

## 运行定位（静态参数；实时状态以current-state和现场检查为准）
- 项目：`E:\共享\创业\01-捞鱼软件产品\sticker-maker`；Python：`sticker_engine/.venv/Scripts/python.exe`。
- 安装路径：`C:\Users\24676\AppData\Local\Programs\sticker-maker-desktop\表情包一键制作.exe`；源码/本机一致实装0.5.14；phase19实际PE/asar/get_version及冻结功能、健康检查通过。此前0.5.12恢复/引擎缺失记录是历史。
- CDP预期`http://127.0.0.1:9487`；phase13已连接并验证命令。实际启动PID在phase13/app-pid.txt；每次续接重新核对，不直接复用旧PID或启动重复实例。
- 资源库root：`E:\共享\星星布丁\微信表情包\周三涵做表情`。
- library_id：`edda8de2-cc2e-4078-921d-96b7962d0a10`；device：`18e5341aea4c413b951b4de6271e599f`；account：`c1d95b6bb285f98ab88f8f519ac0fb9b`。
- 当前canonical episode路径以安装版list_episodes按work_id返回为准，不以旧时间戳路径猜投影目录。
- 操作前确认安装版空闲和library_status可用；上个结果返回后，capture/materialize hooks可能还在运行。
- 生成、元数据、正式投稿使用安装版IPC，不启动第二个生产引擎；独立UI探针仅记录探针，不冒充安装版投稿。
- 不把凭据、storage_state、令牌放进交接文档或共享证据包。

## 优化实验：终态与续接
回执全集：`verification/optimization-phase4-20261014/experiment-NNN.json`、`publish-NNN.json`、`publication-binding-NNN.json`。
已核验投稿均有唯一平台身份，禁止因驱动曾exit1就再发一次。

|候选|类型|work_id|platform_item_id|
|---|---|---|---|
|1|萌系大头|45765ee69d59404dae4a98e64fe7d3ee|stiker_1791922492b735ab2d86b70c51|
|2|标准|25a4c0bb4b094dc885fdf9edc4d31f86|stiker_17919240284c00b95ca1815d6c|
|3|萌系大头|2205569edd6e408895e09675eab744c0|stiker_1791927841670397dd1b866d94|
|4|标准|b2a9a07533c445f88a34836a4c4a6e91|stiker_17919293902520ed54d25d0c37|
|5|萌系大头|d7f88025520f4c3ab2465e9f69f48b5e|stiker_1791930441a75a9712c1baf424|
|6|标准|08a081f361544d16939bfa18f1ca0676|stiker_179193081553afc389036b9a98|
|7|萌系大头|58a469fac56947fd953db5dfdb318b56|stiker_179193536373c9ba17a44b49e5|
|8|标准|75f976fcaff0435dba4d4bdf298e7267|stiker_1791943224613209a297f05e48|

### 候选8：已核验投稿；后续从9萌系大头继续
第8弹真实修复证据在phase12/repair-008.json；32主图/无字图和32备份核验、原图/prompt/评分不变，35/37全部输出匹配预览，封面/图标差异已审阅。
phase13用户恢复引擎后确认混装，备份3份payload后安装同一0.5.13已校验候选包；get_version、资源库和实际投稿流程验证通过，Agent未修改防护配置。
新鲜平台before620作品、608同名0；真实投稿UI成功95.138秒，最初submitted_unverified_id/exit1，随后仅通过新鲜API同步绑定ID stiker_1791943224613209a297f05e48，没有重投。
phase13/platform-after.json核验621平台作品、608唯一、精确标题、16张与16/16含义顺序，Status2待审核；95个保留作品文件SHA不变。
最终安装3份payload仍存在且匹配、引擎命令可用、软件空闲；库635可用+1占位、0作品/设置冲突。旧受阻审计保留，但不作为当前运行状态。
phase13四件证据与仅副本回滚保留本机/云端已投稿；实际1—8已投稿不执行regen_assets，也不删除回执制造新尝试。
0.5.13全网格恢复参数/门禁见[pipeline](../doc/reference/pipeline.md)；第9弹重新实际生成并审阅，不把旧QC或评分复用到新弹。

已存在的驱动（读源代码和既有回执后才按实际请求执行）：
三个scripts驱动仍要求0.5.13，当前本机是0.5.14；继续使用前按真实安装版适配并检验，不直接运行旧版本断言。phase12/publish-recovered.py要求旧0.5.12，仅留作失败恢复历史，不用于当前运行。
```powershell
# 在项目根目录；N为当前请求指定的候选，不盲填8或9
& '.\sticker_engine\.venv\Scripts\python.exe' scripts/generate-optimization-installed.py N
& '.\sticker_engine\.venv\Scripts\python.exe' scripts/publish-optimization-installed.py N
# 仅用于既有UI success=true但ID尚未核验的回执；不重新投稿
& '.\sticker_engine\.venv\Scripts\python.exe' scripts/reconcile-optimization-installed.py N
```
生成脚本的prev.visual_review存在判断不是approved=true；不能据此把未通过候选判为合格。
发布脚本的批准标记必须对应实际视觉审阅和当前SHA；修图后旧批准不复用。
人工/AI分缺失保持null，原始人工评分历史不替代新实验逐弹评分。

## 精选：编号和幂等性
计划：`verification/desktop-issues-20261014/featured-albums.json`（原导入分组，不等于实际投稿编号）。
实际台账：`E:\共享\星星布丁\微信表情包\所有表情\精选\精选上传记录.jsonl`，schema2，424条。
真实短名/详情：`verification/production-phase11-20261014/short-name-plan.json`、`platform-verification.json`、`featured-publish-N.json`、`platform-detail-NNN.json`。

|实际编号|原导入组|work_id|platform_item_id|
|---|---|---|---|
|2|14|0fb88a37e4ad57d596ac867af762b39c|stiker_179193716095bfef9c3af9b431|
|3|16|31ae59578b225cd0bd141b238252b9d2|stiker_17919372856da9ad9527b16078|
|4|17|d816139d4ebd5c13b0643804d001f7a8|stiker_1791937406aaeccd78cee21cea|
|5|18|041473eab0e25e3d8029b89b6320323e|stiker_1791937527296631fb440bab7f|
|6|19|1f0ab3f6a7335793afb899f804a4db18|stiker_1791937647a8d63153fc638557|
|7|20|4ab4959ef4dd50d7a548c76e69615131|stiker_179193776984c680bb422ddf42|
|8|21|7db4416e50c2589a97d61edf1b1ac82f|stiker_179193788981899cfe86a4b6f8|

- 编号1仅预留：旧组13已提交ID stiker_17919324965ba38b7b9e5c801c，原work_id 02bf56febc8d5bb3a47eb0a839ccca6c。
- 旧组13回执在phase9/featured-publish-13.json，state=verified_submitted_name_mismatch；平台实际长名无编号，原素材尚未正确绑定到平台占位。它不是失败可重试的新任务。
- phase9旧publish-featured.py已设旧13防重投；phase11 prepare-short-names.py已经执行过，禁止重新分配2—8编号。
- phase11 publish-short.py的2—8回执均verified_submitted；以后续接要检查终态，不能删除回执/handle制造新尝试。
- 首次短名2投稿20.028秒停在登录前，失败证据featured-publish-2-login-failed.json保留；后续fresh-login.json新鲜确认短名2不存在后才恢复。这个证据不构成以后盲重试依据。
- 原15组上传探针17/20，未保存/提交。probe并未给出每个原文件可用性的可靠身份映射；不能自行声称那17张均已正式投稿。
- 不为规避平台重复检测变换原图；源SHA和已审阅软件资产保留。后续归组先证明来源/数量和必要的平台身份。
- “待审核且QuickModifyValid=0”是已观察状态；旧13改名/身份关联须再核验平台并走正式软件流程，不直接改ID或绕过verify_target。

## 完成状态的判定
|状态|含义与续接动作|
|---|---|
|generated|仅生成；需实际QC，不能记已投稿|
|QC=false|先修复及复核，不提交|
|upload-only|临时接收；saved=false/submitted=false，不能记uploaded=true|
|submitted_unverified_id|已经UI成功；只查新鲜平台身份，不重复提交|
|verified_submitted|已完成投稿核验；保留ID，后续只更新审核状态|
|verified_submitted_name_mismatch|已有真实投稿但命名未完成；保留实际值，不重投|
|unknown/未核销operation|先用新鲜平台查证再核销，不把未知当失败|

## 证据目录路由（只读相关一轮）
- 同步提速：verification/sync-speed-20261013；605状态14.505秒、129理由23.756秒，不是全链路30秒SLA。
- 冲突/空失败目录/评分分析：desktop-issues-20261014、desktop-issues-phase2/phase3-20261014。
- 图像与实装：optimization-phase5、performance-phase6、publication-phase7、production-phase8、selected-phase9、production-phase10-20261014。
- 精选短名/库最近成功快照：production-phase11-20261014；详细报告为VERIFICATION.txt。
- 候选8实际修复/0.5.13测试/投稿失败与恢复安装：grid-gutters-phase12-20261014；逐项JSON/日志，四件代码/修图证据已补齐，但运行恢复和正式投稿未完成。
- 最新运行/第8弹投稿：runtime-resume-phase13-20261014；混装修正、真实运行/平台详情、4文档/3payload/元数据的仅副本回滚。
- 文档checkpoint：docs-checkpoint-20261014-v2；7份文档原SHA、差异、验证与仅副本回滚。
- 本次文档整理：docs-handoff-20261014（五份原入口SHA、无损归档、文档验证和独立副本回滚）。

## 可复用的接力提示词
```text
请接手本项目。本轮任务以我最新请求为准。先读根SKILL.md、docs/agent.md与docs/current-state.md；
如果要继续长任务，再按需读docs/long-task-handoff.md对应小节和它指向的真实回执。
复核当前版本、canonical work_id路径、运行状态与相关终态，不重投已成功/未知结果的作品。
保留原作品、评分、凭据和已有未提交修改；真实分数缺失继续记null。
完成本轮后只更新current-state和roadmap的相关项，详细证据留verification，不重复复制长日志到入口。
```

## phase14评分续接（2026-10-14）
用户选择固定AI分单独记录。规则及复用提示词见[ai-rating-standard.md](ai-rating-standard.md)。1—8实验回执AI字段已填，人工仍null；历史相邻下降真实保留，旧作品不重投。逐图评语/公式/源SHA在verification/ai-review-phase14-20261014；phase12/13的scores=null是当时快照，不是当前状态。候选9先生成/QC，再同规则评审并与第8弹比较。此轮只改外置实验记录与文档，生产作品、应用代码及0.5.13版本未改。

## phase15人工评审纠偏（2026-10-14）
用户明确反馈AI分虚高、基本没有合格，要求每10弹人工查并提供表格。当前AI分仅历史参考；详见[人工评审](human-rating-batches.md)。第9弹609已实际生成16张，未投稿；第一次失败因继承死代理，直连CLI成功后只纠正启动环境重启、再确认终态后重试，未改全局Codex配置/应用代码。评分表含前9实图和第10待生成位置，人工输入空白，不能重跑builder覆盖填写。phase14/本轮早先AI判定不代表人类认可，不再作为发布批准；后续按本批人工反馈修正，每10弹交付检查表。

## phase16首批10弹实图补齐（2026-10-14）
第10弹610标准版，250.353秒真实生成，work_id `6e33aa4cf4cb477ea6d111520734b7a5`；本批5萌系/5标准、160主图/50素材，已投稿仍8。第9、10均未投稿，所有实验人工分仍null，第10AI分也null。
同一人工评分表v1.1已原地编辑；保留既有黄色格、前189图字节/位置及既有布局；公式用临时2分测试后恢复，合格性不从分数推断。
详细证据与独立副本回滚在verification/human-batch-phase16-20261014；应用/实装保持0.5.13，公网仍0.5.1，未改应用代码或原图。
续接提示：先读current-state.md与human-rating-batches.md，接收首批人工评分和主要问题后再调整；不得用旧AI高分批准第9/10投稿或批量推进11—100，空白人工格继续记null。

## phase17精选逐图核验与第9合辑（2026-10-14）
原组15+4尾图逐一试传24项：21接收/3重复，平台作品列表不变；每条绑定实际文件SHA和0/1格，不再把17/20群组数当单图身份。17张组15与3尾图组成精选9，经软件导入/编号/正式提交、随后新鲜详情核验20张/含义20逐字一致。
精选9 work_id `6d631fb188775c8bab46340c477df9d4`、ID `stiker_1791949276ede1c80de2476d6d`，正式回执/原图SHA/未投稿余项在verification/selected-index-phase17-20261014。导入曾遇旧rows缓存，只续接原成功handle并正式materialize，没有重复导入。
实际精选180张、短名160张；系列next_number10，旧13仍待审核/QuickModifyValid0，不改名/重投。剩1尾图和前12组的单图提取/归组未完；100优化实验仍10生成8投稿、等本批人工评分，不推进AI高分流水线。
续接提示：先读本轮逐图回执与最新current-state；待投稿源先逐图证明接收，20张成组、保留源SHA/原分组slot、经软件投稿后只核验ID，上传-only不记uploaded。

## phase20续接：人类通过与平台接收分开
用户已确认8张修正版副本过关，SHA绑定人工记录见phase18/human-approval-20261014.json；原分/原XLSX不变，新数字分为null，未推广为第9/10整弹合格。
前12组240张已完整逐图试传：105接收、135重复，未保存/提交，平台完整ID集合不变；检查已回填真实JSONL（424条/180已投稿/264个individual_upload_checks）。不要重复执行probe或writeback脚本；检查terminal回执及writeback-result。
精选10草稿见phase21/next-selected-plan.json，20张主图、原始含义和女性哇哦封面/图标已看图；尚未导入/提交，next_number仍10。下一轮先捕获phase20后的新台账基线及安装版空闲状态，再按实际SHA/QC与唯一平台身份完成正式发布，不复用phase17旧台账基线。

## phase21续接：精选10已核验终态
精选10 work_id=a17ac2d412255c25932bb9f2a9237994，平台ID=stiker_179195660444acd396c702d589；正式投稿115.162秒，后续仅核验唯一新身份/精确名称/20张及20含义。JSONL424条/200已投稿/264逐图检查，短名2—10共180张合规，selected-short-20261014 next_number11。原阶段草稿/导入/投稿/平台核验回执均在phase21，终态不重新导入或再次提交。
phase20可接收105项减本批20，余85项+phase17尾图1=86；138明确重复（phase20的135+phase17的3）保留证据，不改像素规避。下一轮捕获新的200条已投台账基线；只挑未投、逐图有接收证据、含义真实且组内不重复的20项，尾数不足20不冒充完整弹。100优化实验仍10生成8投稿，后续采用已经通过的文案/主体/残边修正，每10弹人工检查，不复用旧AI高分。

## phase22终态续接：精选11—14已投稿
phase22/batch-run-state.json已terminal，真实11—14共80张发布并核验4个唯一ID；JSONL424条/280已投/264逐图检查，短名2—14共260合规，next_number15。run-batch.py及每弹import/publish/close回执均为终态，不再运行或删handle重投。台账基线200只属于本阶段，下轮基线必须从280真实台账捕获。
未投剩6项已接收和138明确重复；6项保留于batch-plan.json.remaining_accepted，未凑20；重复项不改图规避。100实验仍10生成8投稿、第9/10未投；已通过的8修正版只是SHA绑定单图，不是整批数字评分。下一步可按最新人工反馈修正/核验第9/10候选再推进下一10弹，原评分表不覆盖。保护meta捕获原始字节，之后只允许实测platform_updated_at观测时间变化，任何内容/评分/身份变化要重新审计而不是重写基线。
批次最后必须安装版library_handoff保存共享设置，核对共享系列头payload与本机next_number；本轮本机15/库11的未入库分歧因此消失，新增15头以11头为父，旧3个版本原SHA保留。未完成capture的分歧不能按“随便选最新”处理，真正竞争payload变化需逐字段核验。证据：handoff-response.json、shared-series-new-revisions.json、shared-series-original-hashes.json。
