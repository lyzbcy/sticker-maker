# ChatGPT网页制作：Sticker Maker现有创作分支

唯一维护源为 sticker-maker 仓库的现有 creator/publisher skill 与引擎。先更新整个仓库，再读取对应skill；不单独安装旧 wechat-sticker-web ZIP。素材目录中的入口仅指回本仓库，不维护第二套算法/概率/角色图片。

## 准备与生成

1. 微信本人后台读取完整本系列名单，含草稿与待审，核对账号、最大编号和同名，记录 source_url、checked_at（带时区）、max_episode、verification_note。未知结果先查回执，已有同名目录续接不覆盖。
2. 当前 creator/config.yaml 是本分支唯一概率与服装配置：单人85%、双人15%，单人条件星星布丁75%、捞鱼25%，双人二者。角色图片直接取现有素材，不在skill再打包一份。
3. 在本skill目录执行：

```text
python scripts/web_prepare.py --output-root <素材根> --assets-root <现有base图片目录> --evidence <平台查号.json>
```

证据须1小时内，保存真实随机值、实际base与SHA。平台编号与本地实验冲突时先核实，不把本地最高号当平台结果。

4. 在ChatGPT网页上传所选base，确认附件加载。只框定主题、使用场景、使用人群，其余动作/道具/短字交给模型发挥。默认4×4、16张可独立发的表情、连续白描边、纯洋红背景（角色含洋红则绿色）。仅用户明确要求时走故事分支。
5. 首次生成提示词同时要求生成后在同一响应输出16项JSON：index（左到右、上到下）、text（实际短字，无字为空）、meaning（建议含义）。JSON只作候选，不作为图片真值；未给JSON时在已有审图中记录，不为表格单独重生。
6. 下载本次生成原图至 原图/grid_4x4.png，记录聊天URL和SHA；不取附件/截图代替。更详细网页约束见 [质量细节](chatgpt-web-quality.md)。

## 后处理与审图

在原本就需要的整图审阅中，同时核对角色、16格完整性、文字、候选JSON顺序；写 meanings.json（1—16）。不要固定再做一次识图调用；异常小字才局部放大/按需识读。

```text
python scripts/web_process_grid.py --episode-dir <本弹> --meanings <meanings.json> --outline-px 2
```

直接导入当前引擎grid_cutter与ChromaKeyProvider，不留复制快照。新增白边/边缘去色辅助只维护在 scripts/web_edge_finish.py。观察白/浅灰/深色底效果；alpha合格不等于边缘合格。避免叠加过厚白边，16图词义与顺序复核合并进行。旧最终版非空时拒绝覆盖，先备份并明确修复目标。

## 配套图与真实投稿

从当弹16张成品中选一张正面、完整、无挡脸动作的表情，再用 scripts/web_head_crop.py 按已审polygon截头。头像只能从当弹生成的16张表情中选取，再截完整头部；记录panel_index、源图与裁切SHA及审阅polygon。不得复用base或其他弹头像作为回退。未知或不合格裁切停下修正，不追加头像生图。使用当前引擎make_big_head_cover，240封面直接缩50图标；横幅调用现有make_banner，赞赏图调用当前AssetsStage。不得复制函数或退回旧版make_cover全身缩放。

```text
python scripts/web_publish_assets.py --episode-dir <本弹> --head-source <现有纯头源> --banner-sources <本弹无字源> --tip-source <本弹成品>
```

脚本源路径须在本弹内。替换先备份并加--replace；五项配套图每弹本地重新渲染，禁止固定共享赞赏页。现行引擎赞赏文字字体支持Windows微软雅黑/黑体；其他系统无可用字体时明确阻断，不复制渲染器或静默去字。

完成当前素材SHA视觉复核后，交给原 [publisher微信网页分支](../../lyzbcy-sticker-publisher/reference/wechat-web.md)，按授权实际提审并精确ID回读。36项预检、上传成功或页面保存都不能冒充已上线。

## 实测边界

609/610原ID修复、611/612新投稿已真实回读待审核。611追加生图0次，未代表0 token或量化提速，审核通过与Grok环境仍需单独验证。历史实测见 [回归记录](../../../../docs/wechat-web-skill-pilot-20261105.md)。

## 两弹计时批处理（613/614复盘后）

优先用 scripts/web_batch.cjs，三个阶段为 begin → assets → publish；均在此原skill内，复用当前引擎。begin自动查号、抽样、并行等待两弹网页生成、下载原图、编号切图、输出一次合并审图板。Agent审阅32格后一次写review.json：albums内每项episode、16个meanings、head_index、归一化head_polygon、tip_index、description。assets归一化含义词（啊？→啊）、更名、当弹截头、生成五项配套图和合并素材总览。Agent看完后写approval.json，逐弹approved/head_only/asset_hashes绑定当前发布素材清单，再执行publish。

命令：node scripts/web_batch.cjs begin --config <config.json>；node scripts/web_batch.cjs assets --manifest <manifest.json> --review <review.json>；node scripts/web_batch.cjs publish --manifest <manifest.json> --approval <approval.json>。config为outputRoot、assetsRoot、logDir、accountAnchor及两项themes（theme/scenario/audience）。全过程从begin查号前计时，包含审图和编排等待；开发优化时间另报，不从运行计时中扣去异常。begin未知时读manifest续接，不重新生成。publish的sdk-journal.json存在时拒绝新写入，先按日志ID回读。

禁止在每个SDK步骤间回到Agent手写下一条请求。SDK流水线自动上传、落盘意向、创建、保存、校验32张原始MD5/词义/顺序与五项配套图、每弹仅提交一次，再按ID和同名唯一性回读。浏览器异步任务用启动+轮询，不经桥接直接await长Promise；上传4并发，记录实际完成时间。目标约5分钟是实测目标，不是对外部生图耗时的保证。
