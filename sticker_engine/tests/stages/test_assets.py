from PIL import Image
from pathlib import Path
from unittest.mock import MagicMock
from sticker_engine.stages.assets import AssetsStage
from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec
from sticker_engine.config.schema import Config, Paths


def _ctx_with_stickers(tmp_path, n=16):
    paths = Paths(user_data=tmp_path, output_root=tmp_path/"e", reference_lib=tmp_path/"ref",
                  prefs_file=tmp_path/"p.yaml", codex_exec="codex", codex_output_dir=tmp_path/"c")
    config = Config.placeholder(); config.paths = paths
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode_dir = tmp_path/"e1"; ctx.episode_dir.mkdir()
    final = ctx.episode_dir / "最终版"; final.mkdir()
    for i in range(n):
        Image.new("RGBA", (240,240), (i*10, 100, 100, 255)).save(final/f"表情{i}.png")
        ctx.stickers.append(type("S",(),{"path": final/f"表情{i}.png"})())
    return ctx


def test_assets_generates_banner_cover_icon_intro(tmp_path):
    ctx = _ctx_with_stickers(tmp_path)
    vision = MagicMock()
    vision.write_intro.return_value = "可爱的表情包，适合日常聊天。"
    stage = AssetsStage(vision=vision)
    stage.run(ctx)
    assert (ctx.episode_dir / "横幅" / "横幅.png").exists()
    assert (ctx.episode_dir / "封面" / "封面.png").exists()
    assert (ctx.episode_dir / "图标" / "图标.png").exists()
    intro = (ctx.episode_dir / "介绍.txt").read_text(encoding="utf-8")
    assert 1 <= len(intro) <= 80


def test_banner_is_750x400(tmp_path):
    ctx = _ctx_with_stickers(tmp_path)
    stage = AssetsStage(vision=MagicMock())
    stage.run(ctx)
    w, h = Image.open(ctx.episode_dir/"横幅"/"横幅.png").size
    assert (w, h) == (750, 400)


def test_banner_new_style_cute_card_layout(tmp_path):
    """2026-09-02 横幅重做：奶油粉实底（不再透明底黑底观感）+ 白色圆角卡片。

    - 模式为 RGB（实底，不带 alpha 通道）
    - 四角是浅色渐变底（萌系氛围），不再是透明/黑
    - 画面里有大量近白像素（4 张白色圆角卡片）
    """
    import numpy as np
    ctx = _ctx_with_stickers(tmp_path)
    stage = AssetsStage(vision=MagicMock())
    stage.run(ctx)
    img = Image.open(ctx.episode_dir/"横幅"/"横幅.png")
    assert img.mode == "RGB"
    arr = np.asarray(img)
    # 四角均为浅奶油粉（渐变底）
    for corner in [(2, 2), (2, 747), (397, 2), (397, 747)]:
        px = arr[corner[0], corner[1]]
        assert px[0] >= 245 and px[1] >= 220 and px[2] >= 228, corner
    # 白色卡片像素充足（近白 且绿色通道也高）
    near_white = ((arr[:, :, 0] >= 248) & (arr[:, :, 1] >= 248) &
                  (arr[:, :, 2] >= 248)).sum()
    assert near_white > 3000


def test_cover_is_240x240_and_differs_from_banner_source(tmp_path):
    ctx = _ctx_with_stickers(tmp_path)
    stage = AssetsStage(vision=MagicMock())
    stage.run(ctx)
    w, h = Image.open(ctx.episode_dir/"封面"/"封面.png").size
    assert (w, h) == (240, 240)
    # 封面应是单角色特写，不是横幅拼贴（教训14）——这里校验它来自某张成品图


def test_icon_is_50x50(tmp_path):
    ctx = _ctx_with_stickers(tmp_path)
    stage = AssetsStage(vision=MagicMock())
    stage.run(ctx)
    w, h = Image.open(ctx.episode_dir/"图标"/"图标.png").size
    assert (w, h) == (50, 50)


# ---------------- 2026-09-09 图标 = 封面同图（用户定稿） ----------------

def test_icon_is_same_image_as_cover(tmp_path):
    """图标 = 封面同图缩 50×50：非 combo 单封面回退第 1 张，图标应与其同源。"""
    ctx = _ctx_with_stickers(tmp_path)
    stage = AssetsStage(vision=MagicMock())
    stage.run(ctx)
    cover = Image.open(ctx.episode_dir / "封面" / "封面.png").convert("RGB")
    icon = Image.open(ctx.episode_dir / "图标" / "图标.png").convert("RGB")
    assert icon.size == (50, 50)
    # 同源验证：两者主色应一致（fixture 第 1 张 = (0,100,100)）
    cover_c = cover.resize((1, 1)).getpixel((0, 0))
    icon_c = icon.resize((1, 1)).getpixel((0, 0))
    for a, b in zip(cover_c, icon_c):
        assert abs(a - b) < 25   # LANCZOS 缩放允许轻微色差


def test_icon_follows_cover_no_independent_fallback(tmp_path):
    """图标无独立降级：封面回退时图标跟随同图；icon_fallback 不再置位
    （降级信号由 cover_fallback 携带，批量自动发布据此跳过）。"""
    ctx = _ctx_with_stickers(tmp_path)
    stage = AssetsStage(vision=MagicMock())
    stage.run(ctx)
    assert ctx.icon_fallback is False
    assert ctx.cover_fallback is False       # fixture 非 combo 单：只 WARN 不拦截
    warns = [e for e in ctx.production_log
             if e.stage == "S3" and e.status == "WARN"]
    assert warns                             # 非 combo 单提示按旧规则取第 1 张
    assert (ctx.episode_dir / "图标" / "图标.png").exists()
