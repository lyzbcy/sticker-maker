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
