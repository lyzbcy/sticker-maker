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

从本弹已有header_slots/header_sources.json、_noword选择无字源；不足时审阅原图或同服装base并本地裁头，不默认追加头像生图。使用当前引擎make_big_head_cover，240封面直接缩50图标；横幅调用现有make_banner，赞赏图调用当前AssetsStage。不得复制函数或退回旧版make_cover全身缩放。

```text
python scripts/web_publish_assets.py --episode-dir <本弹> --head-source <现有纯头源> --banner-sources <本弹无字源> --tip-source <本弹成品>
```

脚本源路径须在本弹内。替换先备份并加--replace；五项配套图每弹本地重新渲染，禁止固定共享赞赏页。现行引擎赞赏文字字体支持Windows微软雅黑/黑体；其他系统无可用字体时明确阻断，不复制渲染器或静默去字。

完成当前素材SHA视觉复核后，交给原 [publisher微信网页分支](../../lyzbcy-sticker-publisher/reference/wechat-web.md)，按授权实际提审并精确ID回读。36项预检、上传成功或页面保存都不能冒充已上线。

## 实测边界

609/610原ID修复、611/612新投稿已真实回读待审核。611追加生图0次，未代表0 token或量化提速，审核通过与Grok环境仍需单独验证。历史实测见 [回归记录](../../../../docs/wechat-web-skill-pilot-20261105.md)。
