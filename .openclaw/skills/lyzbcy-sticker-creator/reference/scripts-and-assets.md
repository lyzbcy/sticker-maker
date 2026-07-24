# Scripts And Assets Reference

## 核心脚本

### prep_episode.py

```bash
python prep_episode.py --mode auto --type static
```

作用：
- 创建目录
- 选择角色和参考图
- 生成 `本次制作角色.md`
- 生成 `prep_state.json`

### validate.py

```bash
python validate.py --dir "<表情包目录>" --stage pre_generate
python validate.py --dir "<表情包目录>" --stage post_generate
python validate.py --dir "<表情包目录>" --stage pre_publish
python validate.py --dir "<表情包目录>" --stage full
```

### crop_grid.py

```bash
python crop_grid.py --grid 2 --input quad.png --output ./原图/ --start 1
python crop_grid.py --grid 3 --input grid.png --output ./帧图/1/
python crop_grid.py --grid 4 --input grid.png --output ./原图/
```

## 旧脚本兼容信息

- `crop_4grid.py`：旧四宫格裁剪入口
- `crop_9grid.py`：旧九宫格裁剪入口
- 新流程优先用 `crop_grid.py`

## 发布素材生成

### make_assets.py

```bash
python make_assets.py --dir "E:\星星布丁\微信表情包\周三涵做表情N"
```

### make_banner.py

```bash
python make_banner.py --input-dir 最终版 --output-dir 横幅
python make_banner.py --input 开心比耶.png 委屈.png 真棒.png --output 横幅/横幅.png --style story
```

要求：
- `750x400`
- 默认 `--style auto`：1 张候选时生成第8弹式简约主视觉；3 张候选时生成“表情小剧场”横幅，主角居中、两侧小表情辅助叙事。
- 选图会惩罚整张方图背景、黑色底块、主体贴边，避免横幅像未抠干净的截图。
- 如小剧场效果不如单主角，手动加 `--style simple` 回退安全模板。

### make_cover.py

```bash
python make_cover.py --input 最佳表情图.png --output 封面/封面.png
```

要求：
- `240x240`
- 建议透明背景

### make_icon.py

```bash
python make_icon.py --input 脸部特写.png --output 图标/图标.png
```

要求：
- `50x50`
- 脸部聚焦
- 建议透明背景

### face_detect.py

用途：
- 面部检测
- 头部区域裁剪
- 给图标生成辅助定位

## 宫格模式

| 模式 | 参数 | 输出 |
|------|------|------|
| 2x2 | `--grid 2` | 4 张 |
| 3x3 | `--grid 3` | 9 张 |
| 4x4 | `--grid 4` | 16 张 |

## 动图相关

### make_gif.py

```bash
python make_gif.py --input ./帧图/1/ --output ./1.gif
```

### align_frames.py

用途：
- 对齐帧图
- 减少 GIF 抖动

## 什么时候不要展开本文件

如果当前只是：
- 跑准备
- 跑校验
- 找主流程入口

那只看主 `SKILL.md` 即可，不必先读这份参数细节。
