# -*- coding: utf-8 -*-
"""solid 实底模式回归锁（2026-09-09 批量 3 连败事故）。

事故：solid 分支（2026-09-08 v2 品红→马卡龙染色）首跑即
NameError: name 'np' is not defined——import 用别名 `_np`、使用处写
`np`，transparent 模式从未走过该分支所以没暴露。本测试锁死：
background_mode=solid 时 S2 必须跑通且品红被替换成马卡龙色。
"""
import numpy as np
from PIL import Image
from pathlib import Path
from unittest.mock import MagicMock
from sticker_engine.stages.postprocess import PostprocessStage
from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec
from sticker_engine.config.schema import Config, Paths


def _magenta_grid(path, grid=4, cell=20):
    """品红底宫格：格子间画品红沟，格内放非品红方块（角色位）。"""
    arr = np.zeros((cell * grid, cell * grid, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 2], arr[..., 3] = 255, 255, 255      # 整底品红 #ff00ff
    for r in range(grid):
        for c in range(grid):
            y, x = r * cell, c * cell
            arr[y + 4:y + 16, x + 4:x + 16, 0] = 60           # 蓝色"角色"
            arr[y + 4:y + 16, x + 4:x + 16, 1] = 120
            arr[y + 4:y + 16, x + 4:x + 16, 2] = 220
    Image.fromarray(arr).save(path)


def test_solid_mode_recolors_magenta_and_runs(tmp_path):
    """background_mode=solid：S2 全程跑通（锁 NameError 回归），品红→马卡龙色。"""
    grid_path = tmp_path / "grid_4x4.png"
    _magenta_grid(grid_path, grid=4)
    paths = Paths(user_data=tmp_path, output_root=tmp_path / "e", reference_lib=tmp_path / "ref",
                  prefs_file=tmp_path / "p.yaml", codex_exec="codex", codex_output_dir=tmp_path / "c")
    config = Config.placeholder()
    config.paths = paths
    config.prefs.background_mode = "solid"
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode_dir = tmp_path / "e1"
    ctx.episode_dir.mkdir()
    ctx.grid_image = grid_path
    vision = MagicMock()
    vision.interpret.return_value = {i: f"含义{i}" for i in range(1, 17)}
    stage = PostprocessStage(vision=vision, chromakey=MagicMock())
    stage.run(ctx, gen_mode="keyword_combo", transparent=True)
    assert len(ctx.stickers) == 16
    finals = sorted((ctx.episode_dir / "最终版").glob("*.png"))
    assert len(finals) == 16
    # 品红被染成 PASTEL 首色 (255,214,224)：图里应存在大量该色、几乎无纯品红
    im = np.asarray(Image.open(finals[0]).convert("RGB"))
    pastel = (np.abs(im.astype(int) - np.array([255, 214, 224])).sum(axis=2) < 12).sum()
    magenta = ((im[..., 0] > 240) & (im[..., 2] > 240) & (im[..., 1] < 60)).sum()
    assert pastel > 100, f"品红未被染色（pastel 像素 {pastel}）"
    assert magenta == 0, f"纯品红残留 {magenta} px"


def _soft_grid(path, grid=4, cell=20):
    """AI 直画彩底宫格（v3 形态）：每格柔和蓝底 + 居中角色块，无品红。"""
    arr = np.zeros((cell * grid, cell * grid, 4), dtype=np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3] = 206, 232, 255, 255  # 浅蓝底
    for r in range(grid):
        for c in range(grid):
            y, x = r * cell, c * cell
            arr[y + 5:y + 15, x + 5:x + 15, 0] = 90    # 角色（蓝色块）
            arr[y + 5:y + 15, x + 5:x + 15, 1] = 140
            arr[y + 5:y + 15, x + 5:x + 15, 2] = 230
    Image.fromarray(arr).save(path)


def test_solid_mode_keeps_ai_painted_background(tmp_path):
    """v3：AI 已直画柔和彩底 → S2 原样保留（不染色），配字写上含义词。"""
    grid_path = tmp_path / "grid_4x4.png"
    _soft_grid(grid_path, grid=4, cell=20)
    paths = Paths(user_data=tmp_path, output_root=tmp_path/"e", reference_lib=tmp_path/"ref",
                  prefs_file=tmp_path/"p.yaml", codex_exec="codex", codex_output_dir=tmp_path/"c")
    config = Config.placeholder(); config.paths = paths
    config.prefs.background_mode = "solid"
    config.prefs.sticker_text = True
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode_dir = tmp_path/"e1"; ctx.episode_dir.mkdir()
    ctx.grid_image = grid_path
    vision = MagicMock()
    vision.interpret.return_value = {i: f"含义{i}" for i in range(1, 17)}
    stage = PostprocessStage(vision=vision, chromakey=MagicMock())
    stage.run(ctx, gen_mode="keyword_combo", transparent=True)
    finals = sorted((ctx.episode_dir / "最终版").glob("*.png"))
    assert len(finals) == 16
    im = np.asarray(Image.open(finals[0]).convert("RGB"))
    # 底色保留：四角仍是 AI 的浅蓝 (206,232,255)，未被染成 PASTEL 粉
    corner = im[2, 2]
    assert abs(int(corner[0]) - 206) < 20 and abs(int(corner[2]) - 255) < 20, corner
    # 配字（2026-09-09 定稿样式）：底部红色底条 (232,58,48) + 白色文字像素
    band = im[int(im.shape[0] * 0.82):, :]
    red = ((np.abs(band.astype(int) - np.array([232, 58, 48])).sum(axis=2)) < 60).sum()
    white = ((band > 235).all(axis=2)).sum()
    assert red > 500, f"底部未检出红色底条（{red}）"
    assert white > 30, f"红条上未检出白色文字像素（{white}）"


def test_solid_mode_text_off_keeps_clean(tmp_path):
    """sticker_text=False：不配字，底部带纯净（用户可选关）。"""
    grid_path = tmp_path / "grid_4x4.png"
    _soft_grid(grid_path, grid=4, cell=20)
    paths = Paths(user_data=tmp_path, output_root=tmp_path/"e", reference_lib=tmp_path/"ref",
                  prefs_file=tmp_path/"p.yaml", codex_exec="codex", codex_output_dir=tmp_path/"c")
    config = Config.placeholder(); config.paths = paths
    config.prefs.background_mode = "solid"
    config.prefs.sticker_text = False
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode_dir = tmp_path/"e1"; ctx.episode_dir.mkdir()
    ctx.grid_image = grid_path
    vision = MagicMock()
    vision.interpret.return_value = {i: f"含义{i}" for i in range(1, 17)}
    stage = PostprocessStage(vision=vision, chromakey=MagicMock())
    stage.run(ctx, gen_mode="keyword_combo", transparent=True)
    finals = sorted((ctx.episode_dir / "最终版").glob("*.png"))
    im = np.asarray(Image.open(finals[0]).convert("RGB"))
    band = im[int(im.shape[0] * 0.82):, :]
    red = ((np.abs(band.astype(int) - np.array([232, 58, 48])).sum(axis=2)) < 60).sum()
    assert red == 0, f"关闭配字后仍有红色底条（{red}）"


def test_solid_prompt_uses_ai_painted_background():
    """v3 prompt：solid 模式替换品红行 + 末尾强化块（双处置压先验）。"""
    from sticker_engine.stages.generate import _apply_background_mode
    sample = ("- Background: solid magenta (#ff00ff), completely flat — no shadows, "
              "no gradients, no scenery\n- Absolutely no text")
    out = _apply_background_mode(sample, "solid")
    assert "solid magenta (#ff00ff)" not in out          # 品红行被替换
    assert "REMINDER (background" in out                 # 末尾强化块
    assert "NEVER magenta" in out or "Never magenta" in out
    assert "bottom 18%" in out                           # 留白带（配字位）
    assert "DIFFERENT backgrounds" in out or "independently" in out  # 每格独立
    assert _apply_background_mode(sample, "transparent") == sample  # 透明不动
