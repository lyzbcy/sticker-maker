import pytest
from sticker_engine.story.library import Script
from sticker_engine.story.selector import StorySelector, StoryPoolDepleted


def _make_script(sid, characters):
    panels = [{"cn": f"c{i}", "en": f"e{i}", "emotion": "x", "action": "a"} for i in range(4)]
    return Script(id=sid, name=sid, type="t", characters=characters, panels=panels)


def test_selector_strict_character_match_excludes_mismatched():
    scripts = [
        _make_script("s1", ["星星布丁"]),
        _make_script("s2", ["星星布丁", "捞鱼"]),  # 双人剧本，单人弹不该选
    ]
    sel = StorySelector(scripts, used=set())
    picked = sel.pick(n=1, characters=["星星布丁"])
    assert len(picked) == 1
    assert picked[0].id == "s1"


def test_selector_excludes_used_scripts():
    scripts = [_make_script("s1", ["星星布丁"]), _make_script("s2", ["星星布丁"])]
    sel = StorySelector(scripts, used={"s1"})
    picked = sel.pick(n=1, characters=["星星布丁"])
    assert picked[0].id == "s2"


def test_selector_returns_fewer_when_pool_insufficient():
    scripts = [_make_script("s1", ["星星布丁"])]
    sel = StorySelector(scripts, used=set())
    picked = sel.pick(n=4, characters=["星星布丁"])
    assert len(picked) == 1   # 不足时返回可用的全部，不报错


def test_selector_records_used_after_pick():
    scripts = [_make_script("s1", ["星星布丁"]), _make_script("s2", ["星星布丁"])]
    sel = StorySelector(scripts, used=set())
    sel.pick(n=1, characters=["星星布丁"])
    assert "s1" in sel.used or "s2" in sel.used
    assert len(sel.used) == 1


def test_selector_depleted_returns_empty_triggers_downgrade():
    scripts = [_make_script("s1", ["星星布丁"])]
    sel = StorySelector(scripts, used={"s1"})
    picked = sel.pick(n=4, characters=["星星布丁"])
    assert picked == []   # 空列表 → 调用方降级到排列组合模式
