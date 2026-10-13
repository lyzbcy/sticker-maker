# 封面大头照改造：面部检测方案调研与选型结论（2026-09-08）

## 背景与问题

- 平台驳回复盘（82 单 meta.json）：66+ 单被"聊天页图标：请使用只含有形象
  头部的正面图像做图标 / 去除文字装饰"驳回；封面（240×240 预览图）此前
  = 第 1 张成品直接缩放（`_pick_best_face` 占位实现），全身像头部仅占
  画幅 ~25%，与官方"封面 = 正面半身像"规范不符。
- 需求：量产下用 **0 token** 本地方案保证封面/图标头部占比 ≥75%。

## 候选方案调研（GitHub）

| 方案 | 仓库 | 体积 | 结论 |
|---|---|---|---|
| LBP 动漫脸级联 | [nagadomi/lbpcascade_animeface](https://github.com/nagadomi/lbpcascade_animeface) | xml ~100KB，但需 opencv-python（打包 +60MB） | 备选 Plan B。对 chibi/Q版贴纸检出率一般（训练数据以日漫截图为主） |
| 动漫脸检测+关键点 | [hysts/anime-face-detector](https://github.com/hysts/anime-face-detector) | PyTorch/mmdet 数百 MB | 否决，太重 |
| YOLOv8 动漫脸 | [Fuyucch1/yolov8_animeface](https://github.com/Fuyucch1/yolov8_animeface) | ultralytics + 模型 ~12MB | 否决，引入训练框架依赖 |
| ONNX 动漫脸检测 | deepghs/anime_face_detection（HF） | onnxruntime ~40MB + 模型 ~12MB | 备选 Plan B，最准但依赖重 |
| 轻量真人脸 | [Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB](https://github.com/Linzaer/Ultra-Light-Fast-Generic-Face-Detector-1MB)、YuNet (OpenCV Zoo) | ~1-2MB | 否决，面向真人脸，chibi 失真大 |

## 选型结论：不引入模型，alpha 通道即检测器

本管线产物是**透明底 PNG（S2 洋红抠图后）**——alpha 通道本身就是
100% 准确、零成本的主体分割，比任何人脸检测模型都可靠：

- 主体定位：alpha bbox（非透明底回退边缘中位色差法）
- 头部定位：mask 行宽剖面找肩线（最宽行后的骤减点 = 脖颈，纯 numpy）
- 质量门禁：bbox 形态质检（w/h ≥ 0.65 头肩方格）+ 降级信号外传

外加**生成端已固定 keyword_combo 单尾部 4 格（格 13-16）为 HEAD SHOT**
（头肩占画面 ≥60%、无道具无装饰，`generate.HEADER_SLOTS`，2026-09-05
图标驳回根修，实测头部占比 70%+）——封面/图标直接复用这个洞，无需
从全身像里"检测"头部。

### 何时候重启方案 A（模型检测）

- 生成端 HEADER SHOT 大面积不听话（prompt 失效/模型更换）→
  优先 lbpcascade_animeface（opencv-python-headless 仅作可选依赖
  try-import，缺失走 alpha 回退，不影响打包基线）
- 审核对"正面"判定收紧到五官级 → deepghs ONNX 版（带关键点可验姿态）

## 落地改动（2026-09-08）

| 文件 | 改动 |
|---|---|
| `stages/generate.py` | HEADER_SLOTS/HEADER_EMOS 提升模块级；ctx.header_slots 记录 |
| `stages/assets.py` | `make_big_head_cover`（自适应肩线 zoom-in）+ `pick_header_candidates`（词反查，68 号单同款约定）+ `_is_head_shot` 质检 + `_pick_best_face` 重写 |
| `pipeline/context.py` | `cover_fallback` / `header_slots` 字段 |
| `api.py` | Episode.cover_fallback 透传 |
| `cli.py` | batch 自动发布跳过 cover_fallback 单；regen_assets auto 封面接入 |
| `tests/stages/test_cover_bighead.py` | 4 个回归锁（词反查/后缀变体/产物规格/全身像拦截） |

## 验证记录

- 参数实验：temp/cover_exp/exp2_zoom.png（r=0.88 最佳，r=0.70 切头发顶否决）
- 老单回归：cmp_episode_*.png 四单目测验收；294 新封面头部画幅 ~78-80%
- 引擎测试：失败集合与 baseline 完全一致（零新增失败）
- 上线后：以「周三涵做表情」系列新单审核结果为准（对照 66+ 图标驳回基线）
