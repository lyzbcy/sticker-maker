"""IP 身份门禁测试（2026-08-27 事故：codex 静默丢参考图 → 模型自创角色）。

覆盖：
- 首次校验 YES → 一次生成即通过
- 首次 NO → 强化提示重试；重试 YES → 产出
- 两次 NO → 本单作废（FAIL 日志 + grid_image=None），绝不放行
- 识图无回复 → WARN 放行
- 无 base → 跳过校验
- 重试时 prompt 带 URGENT IDENTITY CORRECTION 前缀、refs 原样再传
"""
from pathlib import Path
from unittest.mock import MagicMock

from sticker_engine.stages.generate import GenerateStage, GenerationMode, _IDENTITY_RETRY_PREFIX
from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec
from sticker_engine.config.schema import Config, Paths


def _ctx(tmp_path):
    paths = Paths(user_data=tmp_path, output_root=tmp_path/"e", reference_lib=tmp_path/"ref",
                  prefs_file=tmp_path/"p.yaml", codex_exec="codex", codex_output_dir=tmp_path/"codex")
    config = Config.placeholder(); config.paths = paths
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode_dir = tmp_path / "e1"; ctx.episode_dir.mkdir()
    (ctx.episode_dir / "原图").mkdir()
    (tmp_path/"ref").mkdir(exist_ok=True)
    ctx.episode.story_mode = False   # 强制 combo，不依赖剧本库
    ctx.selected_characters = ["捞鱼"]
    ctx.selected_bases = [tmp_path / "base.png"]
    (tmp_path / "base.png").write_bytes(b"base")
    return ctx


def _stage(tmp_path, exec_answers):
    fake = MagicMock()
    fake.generate.return_value = tmp_path / "grid.png"
    (tmp_path / "grid.png").write_bytes(b"grid")
    fake.exec_text.side_effect = exec_answers
    return GenerateStage(codex=fake), fake


def test_identity_pass_on_first_check(tmp_path):
    ctx = _ctx(tmp_path)
    stage, fake = _stage(tmp_path, ["YES — same cat character"])
    stage.run(ctx)
    assert ctx.grid_image is not None
    fake.generate.assert_called_once()
    # 校验调用：refs = [grid] + bases
    refs = fake.exec_text.call_args.kwargs.get("refs")
    assert refs and refs[0] == tmp_path / "grid.png" and refs[1] == tmp_path / "base.png"


def test_identity_retry_then_pass(tmp_path):
    ctx = _ctx(tmp_path)
    stage, fake = _stage(tmp_path, ["NO — human girl, not the cat", "YES — correct character"])
    stage.run(ctx)
    assert ctx.grid_image is not None
    assert fake.generate.call_count == 2
    # 第二次 prompt 必须带强化前缀，且 refs 原样再传
    second = fake.generate.call_args_list[1]
    assert second.kwargs["prompt"].startswith(_IDENTITY_RETRY_PREFIX)
    assert second.kwargs["refs"] == [tmp_path / "base.png"]


def test_identity_fail_after_retry_blocks_output(tmp_path):
    ctx = _ctx(tmp_path)
    stage, fake = _stage(tmp_path, ["NO — invented human", "NO — still wrong"])
    stage.run(ctx)
    assert ctx.grid_image is None
    fails = [e for e in ctx.production_log if e.stage == "S1" and e.status == "FAIL"]
    assert any("IP" in e.message for e in fails)
    assert fake.generate.call_count == 2


def test_identity_unparseable_answer_passes_with_warn(tmp_path):
    ctx = _ctx(tmp_path)
    stage, fake = _stage(tmp_path, ["抱歉，我无法确定。"])
    stage.run(ctx)
    assert ctx.grid_image is not None
    warns = [e for e in ctx.production_log if e.stage == "S1" and e.status == "WARN"]
    assert any("IP 校验" in e.message for e in warns)


def test_identity_empty_answer_passes(tmp_path):
    ctx = _ctx(tmp_path)
    stage, fake = _stage(tmp_path, [""])
    stage.run(ctx)
    assert ctx.grid_image is not None
    fake.generate.assert_called_once()


def test_identity_skipped_without_bases(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.selected_bases = []
    ctx.selected_characters = []
    ctx.config.characters = {}
    stage, fake = _stage(tmp_path, [])
    stage.run(ctx)
    assert ctx.grid_image is not None
    fake.exec_text.assert_not_called()


def test_prompt_has_critical_identity_prefix(tmp_path):
    ctx = _ctx(tmp_path)
    stage, fake = _stage(tmp_path, ["YES"])
    prompt, refs = stage._build_prompt_and_refs(ctx, GenerationMode.KEYWORD_COMBO)
    assert prompt.startswith("CRITICAL: draw ONLY the exact character")
    assert "捞鱼" in prompt
    assert "never invent" in prompt
