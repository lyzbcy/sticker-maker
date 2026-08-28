"""系列命名体系 + 作品元数据 + 新 CLI 命令的测试。

用户需求：系列如「周思涵做表情」起始 60 → 专辑名「周思涵做表情 60」，
同系列下一个 61；介绍用系列提示词；素材支持 拼贴/选图/自定义/角色映射。
"""
import json
from pathlib import Path

import pytest

from sticker_engine.config.series import (
    Series, load_series, save_series, find_series, save_series_list_from_dicts,
    EpisodeMeta, load_meta, save_meta, assign_to_series, rename_album,
    mark_published,
)


@pytest.fixture(autouse=True)
def _isolated_user_data(tmp_path, monkeypatch):
    """把 series.json 指到临时目录，避免污染真实用户数据。"""
    import sticker_engine.config.series as series_mod
    monkeypatch.setattr(series_mod, "_series_file", lambda: tmp_path / "series.json")
    return tmp_path


def _make_episode(root: Path, n: int = 4, name: str = "episode_20260825_120000") -> Path:
    from PIL import Image
    ep = root / name
    (ep / "最终版").mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.new("RGBA", (240, 240), (255, 0, 255, 255)).save(ep / "最终版" / f"含义{i}.png")
    (ep / "meaning_map.json").write_text(
        json.dumps({str(i + 1): f"含义{i}" for i in range(n)}, ensure_ascii=False),
        encoding="utf-8")
    (ep / "本次制作角色.md").write_text(
        "# 本次制作角色\n\n角色：星星布丁\n含捞鱼：否\n", encoding="utf-8")
    return ep


# ---------- 系列基础 ----------

def test_series_number_progression():
    s = Series(id="a", name="周思涵做表情", start_number=60)
    assert s.peek_next_number() == 60
    assert s.album_name(s.take_number()) == "周思涵做表情 60"
    assert s.take_number() == 61        # 下一个 61
    assert s.take_number() == 62


def test_save_and_load_series_roundtrip():
    save_series([Series(id="a", name="A系列", start_number=1, next_number=5)])
    loaded = load_series()
    assert len(loaded) == 1
    assert loaded[0].name == "A系列"
    assert loaded[0].next_number == 5
    assert find_series("a").start_number == 1
    assert find_series("nope") is None


def test_save_series_list_preserves_progress():
    """整表保存不丢编号进度（next_number 以已保存的为准）。"""
    save_series([Series(id="a", name="A", start_number=60, next_number=63)])
    save_series_list_from_dicts([{"id": "a", "name": "A改名", "start_number": 60}])
    s = find_series("a")
    assert s.name == "A改名"
    assert s.next_number == 63   # 进度保留


# ---------- episode meta ----------

def test_assign_to_series_names_album(tmp_path):
    ep = _make_episode(tmp_path)
    s = Series(id="z", name="周思涵做表情", start_number=60)
    save_series([s])
    meta = assign_to_series(ep, s)
    assert meta.album_name == "周思涵做表情 60"
    assert meta.number == 60
    save_series([s])   # 保存已推进编号的同一对象
    ep2 = _make_episode(tmp_path, name="episode_20260825_130000")
    meta2 = assign_to_series(ep2, find_series("z"))   # 从磁盘重新加载 → next=61
    assert meta2.album_name == "周思涵做表情 61"


def test_rename_and_mark_published(tmp_path):
    ep = _make_episode(tmp_path)
    meta = rename_album(ep, "我的自定义名字")
    assert load_meta(ep).album_name == "我的自定义名字"
    mark_published(ep)
    m = load_meta(ep)
    assert m.published is True
    assert m.published_at


def test_meta_roundtrip_unknown_keys_ignored():
    m = EpisodeMeta.from_dict({"album_name": "X", "unknown_field": 1})
    assert m.album_name == "X"


# ---------- CLI 命令（走 _handle 测试态） ----------

def _call(handler, args):
    """直接调用 cmd handler，截获 _result 输出。"""
    results = []
    import sticker_engine.cli as cli
    orig = cli._result
    cli._result = lambda req_id, status, data=None, **kw: results.append(
        (status, data if data is not None else kw))
    try:
        handler("req-test", args)
    finally:
        cli._result = orig
    return results


def test_cmd_series_and_episode_flow(tmp_path, monkeypatch):
    from sticker_engine.cli import (cmd_save_series, cmd_list_series,
                                    cmd_get_episode, cmd_update_episode_meta)
    # 引擎输出目录指向临时（list_episodes 用）
    import sticker_engine.cli as cli
    monkeypatch.setattr(cli, "_ensure_engine",
                        lambda: type("E", (), {"config": type("C", (), {
                            "paths": type("P", (), {"output_root": tmp_path})()})()})())
    ep = _make_episode(tmp_path)

    # 1) 建系列
    [(status, data)] = _call(cmd_save_series, {"series": [
        {"name": "周思涵做表情", "start_number": 60}]})
    assert status == "ok"
    sid = data["series"][0]["id"]
    assert data["series"][0]["next_number"] == 60

    # 2) 详情：未命名作品
    [(status, data)] = _call(cmd_get_episode, {"episode_dir": str(ep)})
    assert status == "ok"
    assert data["meta"]["album_name"] == ""
    assert len(data["stickers"]) == 4
    assert data["characters"] == ["星星布丁"]

    # 3) 编入系列 → 自动命名「周思涵做表情 60」
    [(status, data)] = _call(cmd_update_episode_meta, {
        "episode_dir": str(ep), "assign_series_id": sid})
    assert status == "ok"
    assert data["meta"]["album_name"] == "周思涵做表情 60"

    # 4) 系列编号已推进
    [(status, data)] = _call(cmd_list_series, {})
    assert data["series"][0]["next_number"] == 61


def test_cmd_update_intro_and_regen_assets(tmp_path, monkeypatch):
    from sticker_engine.cli import cmd_update_episode_meta
    ep = _make_episode(tmp_path)
    [(status, data)] = _call(cmd_update_episode_meta, {
        "episode_dir": str(ep), "intro": "软萌可爱的一组表情",
        "cover_mode": "pick", "cover_pick": 2, "regen_assets": True})
    assert status == "ok"
    assert (ep / "介绍.txt").read_text(encoding="utf-8") == "软萌可爱的一组表情"
    assert (ep / "封面" / "封面.png").exists()
    assert (ep / "横幅" / "横幅.png").exists()
    assert (ep / "图标" / "图标.png").exists()
    assert load_meta(ep).cover_mode == "pick"


def test_cmd_update_empty_series_name_rejected(tmp_path):
    from sticker_engine.cli import cmd_save_series
    [(status, data)] = _call(cmd_save_series, {"series": [{"name": "  "}]})
    assert status == "fail"
