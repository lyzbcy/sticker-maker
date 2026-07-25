from pathlib import Path
from unittest.mock import MagicMock
import pytest
from sticker_engine.stages.generate import GenerateStage, GenerationMode
from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec
from sticker_engine.config.schema import Config, Paths


def _ctx(tmp_path, refs_available=0):
    paths = Paths(user_data=tmp_path, output_root=tmp_path/"e", reference_lib=tmp_path/"ref",
                  prefs_file=tmp_path/"p.yaml", codex_exec="codex", codex_output_dir=tmp_path/"codex")
    config = Config.placeholder(); config.paths = paths
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode_dir = tmp_path / "e1"; ctx.episode_dir.mkdir()
    (ctx.episode_dir / "原图").mkdir()
    # 参考图
    (tmp_path/"ref").mkdir(exist_ok=True)
    for i in range(refs_available):
        (tmp_path/"ref"/f"r{i}.png").write_bytes(b"x")
    return ctx


def test_decide_mode_picks_ref_library_when_enough_refs(tmp_path):
    stage = GenerateStage(codex=MagicMock())
    ctx = _ctx(tmp_path, refs_available=16)   # grid=4 需 16
    mode = stage.decide_mode(ctx)
    assert mode == GenerationMode.REF_LIBRARY


def test_decide_mode_falls_to_story_when_refs_insufficient(tmp_path):
    stage = GenerateStage(codex=MagicMock())
    ctx = _ctx(tmp_path, refs_available=5)   # < 16
    mode = stage.decide_mode(ctx)
    assert mode == GenerationMode.STORY


def test_decide_mode_falls_to_combo_when_story_disabled(tmp_path):
    stage = GenerateStage(codex=MagicMock())
    ctx = _ctx(tmp_path, refs_available=5)
    ctx.episode.story_mode = False
    mode = stage.decide_mode(ctx)
    assert mode == GenerationMode.KEYWORD_COMBO


def test_generate_calls_codex_and_records_grid_image(tmp_path):
    fake_codex = MagicMock()
    fake_codex.generate.return_value = tmp_path / "fake_grid.png"
    # fake_codex.generate 返回一个路径，GenerateStage 会 shutil.copy2 它，所以要真造个文件
    (tmp_path / "fake_grid.png").write_bytes(b"fake")
    stage = GenerateStage(codex=fake_codex)
    ctx = _ctx(tmp_path, refs_available=0)
    ctx.episode.story_mode = False   # 强制 combo 模式，不依赖剧本库
    stage.run(ctx)
    assert ctx.grid_image is not None
    fake_codex.generate.assert_called_once()


def test_generate_records_fail_and_skips_copy_when_codex_returns_none(tmp_path):
    """补测：codex 生图失败（返回 None）时，记 FAIL 日志、grid_image 置 None、不崩溃。"""
    from sticker_engine.pipeline.context import LogEntry
    fake_codex = MagicMock()
    fake_codex.generate.return_value = None   # 模拟生图失败
    stage = GenerateStage(codex=fake_codex)
    ctx = _ctx(tmp_path, refs_available=0)
    ctx.episode.story_mode = False
    stage.run(ctx)
    assert ctx.grid_image is None
    # 应有一条 S1 FAIL 日志
    fails = [e for e in ctx.production_log if e.stage == "S1" and e.status == "FAIL"]
    assert len(fails) == 1


def test_story_mode_sends_all_selected_character_bases(tmp_path):
    story_selector = MagicMock()
    story_selector.pick.return_value = []
    stage = GenerateStage(codex=MagicMock(), story_selector=story_selector)
    ctx = _ctx(tmp_path)
    ctx.selected_bases = [Path("/tmp/a.png"), Path("/tmp/b.png")]
    ctx.selected_characters = ["甲", "乙"]

    prompt, refs = stage._build_prompt_and_refs(ctx, GenerationMode.STORY)

    assert refs[:2] == ctx.selected_bases
    assert "甲" in prompt and "乙" in prompt
    story_selector.pick.assert_called_once()
    assert story_selector.pick.call_args.kwargs["characters"] == ["甲", "乙"]
