"""codex 参考图 ASCII 暂存 + 网格废图质检测试（2026-08-27 事故修复）。"""
from pathlib import Path

from PIL import Image

from sticker_engine.providers.codex import CodexProvider
from sticker_engine.stages.generate import GenerateStage
from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec
from sticker_engine.config.schema import Config, Paths


def _make_png(path, color_fn):
    im = Image.new("RGB", (64, 64))
    px = im.load()
    for y in range(64):
        for x in range(64):
            px[x, y] = color_fn(x, y)
    im.save(path)


# ---------- ASCII 暂存 ----------

def test_stage_refs_ascii_copies_chinese_path(tmp_path):
    src = tmp_path / "角色" / "捞鱼.png"
    src.parent.mkdir()
    _make_png(src, lambda x, y: (x * 4 % 256, 80, 160))
    p = CodexProvider()
    staged = p._stage_refs_ascii([src])
    assert len(staged) == 1
    s = str(staged[0])
    assert s.isascii()
    assert staged[0].read_bytes() == src.read_bytes()   # 内容一致


def test_stage_refs_ascii_passthrough_ascii_path(tmp_path):
    src = tmp_path / "plain_base.png"
    _make_png(src, lambda x, y: (200, 0, 200))
    p = CodexProvider()
    staged = p._stage_refs_ascii([src])
    assert staged == [src]   # 已是 ASCII：不复制


def test_stage_refs_ascii_drops_missing_file(tmp_path):
    p = CodexProvider()
    staged = p._stage_refs_ascii([tmp_path / "not_exist.png", tmp_path])
    assert staged == []


# ---------- prompt 单行拍平（codex.cmd 多行参数会丢 -i 图片） ----------

def test_build_generate_command_flattens_newlines():
    from sticker_engine.providers.codex import CodexProvider
    p = CodexProvider(codex_exec="codex")
    multi = "line1\nline2\n\nline3"
    cmd = p.build_generate_command(multi, refs=[])
    prompt_arg = cmd[cmd.index("read-only") + 1]   # prompt 在 flags 之后、-i 之前
    assert prompt_arg == "line1 line2 line3"


def test_flatten_prompt_helper():
    from sticker_engine.providers.codex import _flatten_prompt
    assert _flatten_prompt("a\nb\n\nc") == "a b c"
    assert _flatten_prompt("already flat") == "already flat"
    assert _flatten_prompt("") == ""


# ---------- 网格质检 ----------

def test_grid_sanity_rejects_solid_black(tmp_path):
    black = tmp_path / "black.png"
    _make_png(black, lambda x, y: (0, 0, 0))
    stage = GenerateStage(codex=None)
    assert stage._grid_sanity_ok(black) is False


def test_grid_sanity_rejects_solid_white(tmp_path):
    white = tmp_path / "white.png"
    _make_png(white, lambda x, y: (255, 255, 255))
    stage = GenerateStage(codex=None)
    assert stage._grid_sanity_ok(white) is False


def test_grid_sanity_accepts_detailed_image(tmp_path):
    grid = tmp_path / "grid.png"
    _make_png(grid, lambda x, y: ((x * 37) % 256, (y * 53) % 256, (x * y) % 256))
    stage = GenerateStage(codex=None)
    assert stage._grid_sanity_ok(grid) is True


def test_run_retries_and_fails_on_black_grid(tmp_path):
    """黑图两次 → 本单作废，不进 S2。"""
    from unittest.mock import MagicMock
    black = tmp_path / "grid.png"
    _make_png(black, lambda x, y: (0, 0, 0))
    fake = MagicMock()
    fake.generate.return_value = black
    paths = Paths(user_data=tmp_path, output_root=tmp_path/"e", reference_lib=tmp_path/"ref",
                  prefs_file=tmp_path/"p.yaml", codex_exec="codex", codex_output_dir=tmp_path/"c")
    config = Config.placeholder(); config.paths = paths
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode_dir = tmp_path / "e1"; ctx.episode_dir.mkdir()
    (ctx.episode_dir / "原图").mkdir()
    (tmp_path/"ref").mkdir(exist_ok=True)
    ctx.episode.story_mode = False
    stage = GenerateStage(codex=fake)
    stage.run(ctx)
    assert ctx.grid_image is None
    assert fake.generate.call_count == 2   # 重试了一次
    fails = [e for e in ctx.production_log if e.stage == "S1" and e.status == "FAIL"]
    assert any("废图" in e.message or "未通过" in e.message for e in fails)
