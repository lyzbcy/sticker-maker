"""Prompt 方案数据化 + 打分系统测试（2026-08-28）。"""
import json
from pathlib import Path
from unittest.mock import MagicMock

from sticker_engine.config.prompts import (
    BUILTIN_ID, PromptSet, apply_set, builtin_set, delete_set, find_set,
    list_sets, save_set)
from sticker_engine.resources.prompts.templates import _STYLE_BLOCK


# ---------- 方案存取 ----------

def test_builtin_set_always_available(tmp_path):
    sets = list_sets(tmp_path)
    assert sets[-1].id == BUILTIN_ID
    assert "oversized head" in sets[-1].style_block


def test_save_and_find_set(tmp_path):
    ps = save_set(tmp_path, {"name": "黏土风", "style_block": "clay style\n",
                             "combo_extra": "extra combo rule"})
    found = find_set(tmp_path, ps.id)
    assert found.name == "黏土风"
    assert found.combo_extra == "extra combo rule"


def test_find_unknown_falls_back_to_builtin(tmp_path):
    assert find_set(tmp_path, "no-such-id").id == BUILTIN_ID
    assert find_set(tmp_path, None).id == BUILTIN_ID


def test_delete_set_builtin_forbidden(tmp_path):
    ps = save_set(tmp_path, {"name": "临时"})
    assert delete_set(tmp_path, ps.id) is True
    assert delete_set(tmp_path, BUILTIN_ID) is False


def test_apply_set_overrides_style_and_appends_extra():
    ps = PromptSet(id="t", name="t", style_block="MY STYLE BLOCK\n",
                   combo_extra="MY COMBO EXTRA")
    out = apply_set("keyword_combo", ps)
    assert "MY STYLE BLOCK" in out
    assert _STYLE_BLOCK not in out
    assert "MY COMBO EXTRA" in out
    assert "{grid}x{grid}" in out          # 格式化占位符保留
    # 其他模式不受 combo_extra 影响
    out_story = apply_set("story", ps)
    assert "MY COMBO EXTRA" not in out_story


def test_apply_set_with_empty_extras_keeps_template():
    out = apply_set("story", PromptSet(id="t", name="t"))
    assert "{stories_description}" in out


# ---------- 生成链路：方案生效 + prompt 落盘 ----------

def _ctx(tmp_path):
    from sticker_engine.pipeline.context import PipelineContext, EpisodeSpec
    from sticker_engine.config.schema import Config, Paths
    paths = Paths(user_data=tmp_path, output_root=tmp_path / "e",
                  reference_lib=tmp_path / "reference_library",
                  prefs_file=tmp_path / "p.yaml", codex_exec="codex",
                  codex_output_dir=tmp_path / "c")
    config = Config.placeholder()
    config.paths = paths
    config.prefs.ref_lib_priority = False
    config.prefs.story_mode = False
    ctx = PipelineContext(config=config, episode=EpisodeSpec.placeholder())
    ctx.episode.story_mode = False
    ctx.episode_dir = tmp_path / "e1"
    ctx.episode_dir.mkdir(exist_ok=True)
    (ctx.episode_dir / "原图").mkdir(exist_ok=True)
    return ctx


def _ok_codex(tmp_path):
    from PIL import Image
    grid = tmp_path / "grid.png"
    im = Image.new("RGB", (200, 200))
    px = im.load()
    for y in range(200):
        for x in range(200):
            px[x, y] = ((x * 7) % 256, (y * 11) % 256, ((x * y) // 8) % 256)
    im.save(grid)
    fake = MagicMock()
    fake.generate.return_value = grid
    fake.exec_text.return_value = "YES"
    return fake


def test_generate_uses_active_set_and_persists_prompt(tmp_path):
    ps = save_set(tmp_path, {"name": "测试方案", "style_block": "MARKER-STYLE\n",
                             "combo_extra": "MARKER-EXTRA"})
    ctx = _ctx(tmp_path)
    ctx.config.prefs.prompt_set_id = ps.id
    from sticker_engine.stages.generate import GenerateStage
    stage = GenerateStage(codex=_ok_codex(tmp_path))
    stage.run(ctx)
    sent_prompt = stage.codex.generate.call_args.kwargs["prompt"]
    assert "MARKER-STYLE" in sent_prompt and "MARKER-EXTRA" in sent_prompt
    # prompt 落盘（含模式头）
    pfile = ctx.episode_dir / "原图" / "prompt.txt"
    assert pfile.exists()
    content = pfile.read_text(encoding="utf-8")
    assert content.startswith("# mode: keyword_combo")
    assert "MARKER-STYLE" in content


# ---------- 打分往返 ----------

def test_rating_roundtrip_with_production_context(tmp_path):
    import subprocess, sys, os
    ctx = _ctx(tmp_path)
    # 造成品 + 含义 + 角色卡 + prompt 落盘
    final = ctx.episode_dir / "最终版"
    final.mkdir(exist_ok=True)
    (final / "开心.png").write_bytes(b"png")
    (ctx.episode_dir / "meaning_map.json").write_text(
        json.dumps({"1": "开心"}, ensure_ascii=False), encoding="utf-8")
    (ctx.episode_dir / "本次制作角色.md").write_text(
        "角色：星星布丁\n含捞鱼：否", encoding="utf-8")
    (ctx.episode_dir / "原图" / "prompt.txt").write_text(
        "# mode: keyword_combo\n# prompt_set: x (y)\nREAL PROMPT HERE",
        encoding="utf-8")
    env = {**os.environ, "STICKER_ENGINE_USER_DATA": str(tmp_path)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "sticker_engine.cli"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=Path(__file__).parent.parent.parent, env=env)
    out, _ = proc.communicate(input=json.dumps({
        "id": "r1", "cmd": "save_rating",
        "args": {"episode_dir": str(ctx.episode_dir), "overall": 4,
                 "note": "整体不错",
                 "ratings": {"开心": {"score": 5, "note": "很萌"}}}}) + "\n",
        timeout=60)
    res = [json.loads(l) for l in out.strip().split("\n")
           if l.strip() and json.loads(l).get("id") == "r1"
           and json.loads(l).get("type") == "result"][0]
    assert res["status"] == "ok"
    saved = json.loads(Path(res["data"]["path"]).read_text(encoding="utf-8"))
    assert saved["ratings"]["开心"]["score"] == 5
    assert saved["overall"] == 4
    # 生产上下文齐全：单文件即可发给 AI
    assert saved["production"]["mode"] == "keyword_combo"
    assert "REAL PROMPT HERE" in saved["production"]["prompt_file_content"]
    assert saved["production"]["meaning_map"] == {"1": "开心"}
    assert "星星布丁" in saved["production"]["characters"]
