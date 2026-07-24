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
