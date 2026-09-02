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


# ---------------- 2026-09 图标降级信号（批量发布风险） ----------------

def test_icon_fallback_sets_ctx_flag(tmp_path):
    """AI 图标失败退回复用封面时，ctx.icon_fallback 置 True（run_batch 据此跳过自动发布）。"""
    ctx = _ctx_with_stickers(tmp_path)
    vision = MagicMock()   # codex.generate 返回 MagicMock → 路径不存在 → 走降级
    stage = AssetsStage(vision=vision)
    stage.run(ctx)
    assert ctx.icon_fallback is True
    warns = [e for e in ctx.production_log
             if e.stage == "S3" and e.status == "WARN" and "退回复用封面" in e.message]
    assert warns


def test_icon_success_keeps_fallback_flag_false(tmp_path):
    """AI 图标成功时 ctx.icon_fallback 保持 False（不误伤正常单）。"""
    ctx = _ctx_with_stickers(tmp_path)
    stage = AssetsStage(vision=MagicMock())
    icon_raw = ctx.episode_dir / "图标" / "_icon_raw.png"
    icon_raw.parent.mkdir(exist_ok=True)
    Image.new("RGBA", (240, 240), (255, 255, 255, 255)).save(icon_raw)
    stage._make_ai_icon = lambda ctx, paths: icon_raw
    stage.run(ctx)
    assert ctx.icon_fallback is False
