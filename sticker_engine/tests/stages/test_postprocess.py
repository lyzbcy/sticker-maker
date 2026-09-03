import numpy as np
from PIL import Image
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from sticker_engine.stages.postprocess import PostprocessStage, should_chromakey, should_crop
from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec
from sticker_engine.config.schema import Config, Paths


def test_should_crop_true_when_grid_gt_1():
    assert should_crop(grid_size=4) is True
    assert should_crop(grid_size=2) is True


def test_should_crop_false_when_grid_1():
    assert should_crop(grid_size=1) is False


def test_should_chromakey_false_for_ref_library_mode_without_transparent():
    # 参考图库模式 + transparent=False → 不抠
    assert should_chromakey(mode="ref_library", transparent=False) is False


def test_should_chromakey_true_for_prompt_modes():
    assert should_chromakey(mode="story", transparent=True) is True
    assert should_chromakey(mode="keyword_combo", transparent=True) is True


def test_should_chromakey_true_for_ref_library_with_transparent_flag():
    assert should_chromakey(mode="ref_library", transparent=True) is True


def _noop_chromakey():
    """返回一个 passthrough chromakey mock：remove_key_auto 原样返回输入图。
    真实 ChromaKeyProvider.remove_key_auto 返回 PIL Image，所以这里按契约返回
    输入图本身（= 不真抠图，避免算法干扰裁切/落盘测试）。"""
    ck = MagicMock()
    ck.remove_key_auto.side_effect = lambda img: img
    return ck


def _make_grid_image(path, grid=4):
    """造一张 N×N 宫格图，每格不同颜色。"""
    cell = 20
    arr = np.zeros((cell*grid, cell*grid, 4), dtype=np.uint8)
    for r in range(grid):
        for c in range(grid):
            arr[r*cell:(r+1)*cell, c*cell:(c+1)*cell] = (r*30, c*30, 100, 255)
    Image.fromarray(arr).save(path)


def test_postprocess_crops_4x4_to_16_and_writes_meanings(tmp_path):
    grid_path = tmp_path / "grid_4x4.png"
    _make_grid_image(grid_path, grid=4)
    paths = Paths(user_data=tmp_path, output_root=tmp_path/"e", reference_lib=tmp_path/"ref",
                  prefs_file=tmp_path/"p.yaml", codex_exec="codex", codex_output_dir=tmp_path/"c")
    config = Config.placeholder(); config.paths = paths
    config.prefs.vision_calls = True   # S2 识图路径测试（0token 模式走预置词条）
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode_dir = tmp_path/"e1"; ctx.episode_dir.mkdir()
    ctx.grid_image = grid_path
    vision = MagicMock()
    vision.interpret.return_value = {i: f"含义{i}" for i in range(1, 17)}
    stage = PostprocessStage(vision=vision, chromakey=_noop_chromakey())
    stage.run(ctx, gen_mode="story", transparent=True)
    assert len(ctx.stickers) == 16
    assert ctx.meaning_map[1] == "含义1"
    # 最终版目录有 16 张
    final_dir = ctx.episode_dir / "最终版"
    assert len(list(final_dir.glob("*.png"))) == 16


def test_postprocess_skips_crop_for_grid_1(tmp_path):
    grid_path = tmp_path / "grid_1x1.png"
    _make_grid_image(grid_path, grid=1)
    paths = Paths(user_data=tmp_path, output_root=tmp_path/"e", reference_lib=tmp_path/"ref",
                  prefs_file=tmp_path/"p.yaml", codex_exec="codex", codex_output_dir=tmp_path/"c")
    config = Config.placeholder(); config.paths = paths
    config.prefs.vision_calls = True   # S2 识图路径测试（0token 模式走预置词条）
    ctx = PipelineContext(config=config, episode=EpisodeSpec(grid_size=1))
    ctx.episode_dir = tmp_path/"e1"; ctx.episode_dir.mkdir()
    ctx.grid_image = grid_path
    vision = MagicMock()
    vision.interpret.return_value = {1: "单张"}
    stage = PostprocessStage(vision=vision, chromakey=_noop_chromakey())
    stage.run(ctx, gen_mode="keyword_combo", transparent=False)
    assert len(ctx.stickers) == 1
