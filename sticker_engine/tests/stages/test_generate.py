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


def test_keywords_no_banned_low_rating_entries():
    """2026-09-02 评分复盘锁：低分重灾词条不得回流 keywords.json。

    灵魂出窍（1分x5 "跟鬼一样/不许做死人"）、石化（1分x3 "把石化
    扔出去"）、融化系（"把融化删了/不要融化/腿呢"）、吃撑大肚
    （"恶意丑化…露个大肚子"）。
    """
    import json
    import sticker_engine as se
    kw = json.loads((se.resources_path() / "keywords.json").read_text(
        encoding="utf-8"))
    banned_words = ("soul leaving body", "petrified", "overheated",
                    "stuffed and happy", "sleepy melt",
                    "melting into a puddle", "squished flat")
    blob = json.dumps(kw, ensure_ascii=False).lower()
    for w in banned_words:
        assert w not in blob, f"低分词条 {w} 回流了 keywords.json"
    # 描写级禁词也一并锁死（融化/鬼/大肚子/满脸红）
    for w in ("melt", "ghost", "belly round", "tomato-red", "face flushed red",
              "face bright red", "hair standing on end"):
        assert w not in blob, f"低分描写 {w} 回流了 keywords.json"


def test_combo_panels_contain_cute_guard(tmp_path):
    """内置方案 STYLE 块必须带"可爱优先"负面约束（不可爱/吓人反馈）。"""
    from sticker_engine.config.prompts import builtin_set, apply_set
    prompt = apply_set("keyword_combo", builtin_set())
    assert "CUTE and lovable" in prompt
    assert "ghostly" in prompt


# ---------------- 2026-09 主题抽取（400 单量产多样性） ----------------

def _theme_kws(n_per=12, n_themes=3):
    """构造 themes 结构的 keywords：n_themes 个主题各 n_per 条，en 带主题前缀便于归属统计。"""
    themes = {}
    for t in range(n_themes):
        themes[f"主题{t}"] = [
            {"en": f"e{t}-{i}", "desc": f"desc e{t}-{i}", "zh": f"词{t}-{i}"}
            for i in range(n_per)]
    return {"themes": themes, "actions": ["waving"], "props": []}


def _reset_last_theme(monkeypatch):
    import sticker_engine.stages.generate as G
    monkeypatch.setattr(G, "_LAST_THEME_KEY", None)


def test_themed_combo_locks_one_theme(tmp_path, monkeypatch):
    """主题抽取：16 格中主主题占 10-12 格（~70%），其余跨主题点缀。"""
    _reset_last_theme(monkeypatch)
    from collections import Counter
    stage = GenerateStage(codex=MagicMock(), keywords=_theme_kws(), seed=7)
    ctx = _ctx(tmp_path)
    msgs = []
    ctx.stage_progress = msgs.append
    text = stage._random_combo_panels(ctx, 16)
    lines = text.strip().splitlines()
    assert len(lines) == 16
    counts = Counter()
    for ln in lines:   # 行首 "1. E0-3: desc e0-3"，en 前缀标识主题归属
        for t in range(3):
            if f". E{t}-" in ln:
                counts[t] += 1
    assert sum(counts.values()) == 16
    main_count = counts.most_common(1)[0][1]
    assert 10 <= main_count <= 12, counts
    assert any("本单主题" in m for m in msgs)


def test_themed_combo_avoids_repeating_theme_between_runs(tmp_path, monkeypatch):
    """连续两单不选同一主题（跨单类级记忆）。"""
    _reset_last_theme(monkeypatch)
    stage = GenerateStage(codex=MagicMock(), keywords=_theme_kws(), seed=11)
    ctx = _ctx(tmp_path)
    picked = []
    for _ in range(2):
        msgs = []
        ctx.stage_progress = msgs.append
        stage._random_combo_panels(ctx, 16)
        m = next(x for x in msgs if "本单主题" in x)
        picked.append(m.split("「")[1].split("」")[0])
    assert picked[0] != picked[1]


def test_old_keywords_structure_without_themes_still_works(tmp_path, monkeypatch):
    """旧结构兼容：读不到 themes 时退回 emotions 均匀抽（str/dict 混合）。"""
    _reset_last_theme(monkeypatch)
    kws = {"emotions": ["happy", {"en": "sad", "desc": "droopy ears and wobbly lips"}],
           "actions": []}
    stage = GenerateStage(codex=MagicMock(), keywords=kws, seed=3)
    ctx = _ctx(tmp_path)
    text = stage._random_combo_panels(ctx, 5)
    lines = text.strip().splitlines()
    assert len(lines) == 5
    assert any(". Happy:" in ln for ln in lines)
    assert any(". Sad: droopy ears" in ln for ln in lines)


def test_small_theme_pool_refills_to_fill_n(tmp_path, monkeypatch):
    """主题池小于需求时重新装填，保证凑满 n 格（不崩、不缺格）。"""
    _reset_last_theme(monkeypatch)
    themes = {
        "小池": [{"en": f"a{i}", "desc": f"small pool {i}", "zh": f"甲{i}"} for i in range(3)],
        "大池": [{"en": f"b{i}", "desc": f"big pool {i}", "zh": f"乙{i}"} for i in range(12)],
    }
    stage = GenerateStage(codex=MagicMock(), keywords={"themes": themes}, seed=5)
    text = stage._random_combo_panels(_ctx(tmp_path), 9)
    assert len(text.strip().splitlines()) == 9


def test_keywords_resource_has_themes_and_zh():
    """资源锁：keywords.json 升级为 themes 结构，主题 15+、主题词条 200+、全带 zh。"""
    import json
    import sticker_engine as se
    kw = json.loads((se.resources_path() / "keywords.json").read_text(encoding="utf-8"))
    themes = kw["themes"]
    assert len(themes) >= 15
    total = sum(len(v) for v in themes.values())
    assert total >= 200, f"主题词条仅 {total} 条"
    assert len(kw["emotions"]) >= 78   # 通用池保留（旧结构兼容的退路）
    for name, entries in themes.items():
        assert len(entries) >= 10, f"主题 {name} 词条过少：{len(entries)}"
        for e in entries:
            assert e.get("en") and e.get("desc") and e.get("zh"), f"{name}: {e}"
