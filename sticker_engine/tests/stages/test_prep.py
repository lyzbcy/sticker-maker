from pathlib import Path
from unittest.mock import MagicMock
from sticker_engine.stages.prep import PrepStage, PrepResult
from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec
from sticker_engine.config.schema import Config, Paths


def _ctx(tmp_path):
    paths = Paths(
        user_data=tmp_path, output_root=tmp_path/"episodes",
        reference_lib=tmp_path/"ref", prefs_file=tmp_path/"p.yaml",
        codex_exec="codex", codex_output_dir=tmp_path/"codex")
    config = Config.placeholder()
    config.paths = paths
    return PipelineContext(config=config, episode=EpisodeSpec.placeholder())


def test_prep_creates_episode_dir_and_standard_subdirs(tmp_path):
    stage = PrepStage()
    ctx = _ctx(tmp_path)
    stage.run(ctx)
    assert ctx.episode_dir is not None
    assert ctx.episode_dir.exists()
    for sub in ["原图", "最终版"]:
        assert (ctx.episode_dir / sub).exists()


def test_prep_writes_character_card(tmp_path):
    stage = PrepStage()
    ctx = _ctx(tmp_path)
    stage.run(ctx)
    assert (ctx.episode_dir / "本次制作角色.md").exists()


def test_prep_auto_creates_reference_library_if_missing(tmp_path):
    """初心第31行：参考图库文件夹不存在时自动创建。"""
    stage = PrepStage()
    ctx = _ctx(tmp_path)
    # reference_lib 指向一个还不存在的路径
    assert not ctx.config.paths.reference_lib.exists()
    stage.run(ctx)
    assert ctx.config.paths.reference_lib.exists()
    assert ctx.config.paths.reference_lib.is_dir()


def test_prep_does_not_touch_existing_reference_library(tmp_path):
    """参考图库已存在时保持原样（不报错、不重建）。"""
    stage = PrepStage()
    ctx = _ctx(tmp_path)
    ref_lib = ctx.config.paths.reference_lib
    ref_lib.mkdir(parents=True)
    (ref_lib / "existing.png").write_bytes(b"x")
    stage.run(ctx)
    assert (ref_lib / "existing.png").exists()   # 原文件还在
