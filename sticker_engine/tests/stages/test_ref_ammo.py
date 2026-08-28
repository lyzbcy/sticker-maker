"""参考图弹药模型测试（2026-08-27 产品定型：用完即走 + 打完补弹）。

- 归档：参考图模式成功后，用过的库图移入 _used_日期/（base 不动、失败不消耗、关开关不归档）
- 补弹：replenish_refs 感知哈希去重（与在役/归档雷同的不导）
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image

from sticker_engine.stages.generate import GenerateStage, GenerationMode
from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec
from sticker_engine.config.schema import Config, Paths


def _make_sticker(path, seed):
    """不同 seed 生成内容不同的贴纸（dhash 可区分）。"""
    im = Image.new("RGB", (64, 64))
    px = im.load()
    for y in range(64):
        for x in range(64):
            px[x, y] = ((x * seed) % 256, (y * 3) % 256, ((x + y) * seed) % 256)
    im.save(path)


def _ctx(tmp_path, refs_n=16, consume=True):
    # 用引擎默认解析出的库名（CLI 子进程按 user_data/reference_library 找）
    ref_lib = tmp_path / "reference_library"
    ref_lib.mkdir(exist_ok=True)
    for i in range(refs_n):
        _make_sticker(ref_lib / f"r{i}.png", i + 1)
    paths = Paths(user_data=tmp_path, output_root=tmp_path / "e", reference_lib=ref_lib,
                  prefs_file=tmp_path / "p.yaml", codex_exec="codex",
                  codex_output_dir=tmp_path / "c")
    config = Config.placeholder()
    config.paths = paths
    config.prefs.ref_lib_priority = True
    config.prefs.ref_consume = consume
    config.prefs.story_mode = False
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode.story_mode = False    # 决策看 episode 意图（cmd_run 会从 prefs 带入）
    ctx.episode_dir = tmp_path / "e1"
    ctx.episode_dir.mkdir(exist_ok=True)
    (ctx.episode_dir / "原图").mkdir(exist_ok=True)
    return ctx, ref_lib


def _ok_codex(tmp_path):
    grid = tmp_path / "grid.png"
    # 内容丰富的网格（过废图质检：非纯色）
    im = Image.new("RGB", (400, 400))
    px = im.load()
    for y in range(400):
        for x in range(400):
            px[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x * y) // 8) % 256)
    im.save(grid)
    fake = MagicMock()
    fake.generate.return_value = grid
    fake.exec_text.return_value = "YES"
    return fake


def test_used_refs_archived_after_success(tmp_path):
    ctx, ref_lib = _ctx(tmp_path, refs_n=18)
    stage = GenerateStage(codex=_ok_codex(tmp_path))
    stage.run(ctx)
    assert ctx.gen_mode == "ref_library"
    used_dirs = list(ref_lib.glob("_used_*"))
    assert len(used_dirs) == 1
    archived = list(used_dirs[0].glob("*.png"))
    assert len(archived) == 16                      # 用掉 16 张
    remaining = [p for p in ref_lib.iterdir() if p.suffix == ".png"]
    assert len(remaining) == 2                      # 剩 2 张


def test_refs_not_consumed_when_consume_off(tmp_path):
    ctx, ref_lib = _ctx(tmp_path, refs_n=18, consume=False)
    stage = GenerateStage(codex=_ok_codex(tmp_path))
    stage.run(ctx)
    assert not list(ref_lib.glob("_used_*"))
    assert len([p for p in ref_lib.iterdir() if p.suffix == ".png"]) == 18


def test_refs_not_consumed_when_gen_fails(tmp_path):
    ctx, ref_lib = _ctx(tmp_path, refs_n=18)
    fake = MagicMock()
    fake.generate.return_value = None               # 生图失败
    stage = GenerateStage(codex=fake)
    stage.run(ctx)
    assert ctx.grid_image is None
    assert not list(ref_lib.glob("_used_*"))        # 弹药没打出去，不消耗


def test_story_mode_does_not_archive(tmp_path):
    """非参考图模式没有库图可归档，不应创建 _used_ 目录。"""
    ctx, ref_lib = _ctx(tmp_path, refs_n=3)         # 3 < 16 → 走 combo
    stage = GenerateStage(codex=_ok_codex(tmp_path))
    stage.run(ctx)
    assert ctx.gen_mode == "keyword_combo"
    assert not list(ref_lib.glob("_used_*"))
    assert len([p for p in ref_lib.iterdir() if p.suffix == ".png"]) == 3


def test_replenish_refs_dedup_and_import(tmp_path):
    """回流：新内容导入、与库/归档雷同的跳过。"""
    import subprocess, sys, os
    ctx, ref_lib = _ctx(tmp_path, refs_n=2)
    # 作品成品：1 张新内容 + 1 张与库内 r0 完全同图（雷同）
    final = tmp_path / "e1" / "最终版"
    final.mkdir(parents=True, exist_ok=True)
    _make_sticker(final / "新贴纸.png", 999)
    Image.open(ref_lib / "r0.png").save(final / "复制贴纸.png")

    env = {**os.environ, "STICKER_ENGINE_USER_DATA": str(tmp_path)}
    proc = subprocess.Popen([sys.executable, "-m", "sticker_engine.cli"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True,
                            cwd=Path(__file__).parent.parent.parent, env=env)
    out, _ = proc.communicate(input=json.dumps(
        {"id": "r1", "cmd": "replenish_refs",
         "args": {"episode_dir": str(ctx.episode_dir)}}) + "\n", timeout=60)
    res = [json.loads(l) for l in out.strip().split("\n")
           if l.strip() and json.loads(l).get("id") == "r1"
           and json.loads(l).get("type") == "result"][0]
    assert res["status"] == "ok"
    assert "新贴纸.png" in res["data"]["imported"]
    names_skipped = [s["name"] for s in res["data"]["skipped"]]
    assert "复制贴纸.png" in names_skipped
    assert (ref_lib / "新贴纸.png").exists()
    assert res["data"]["library_count"] == 3
