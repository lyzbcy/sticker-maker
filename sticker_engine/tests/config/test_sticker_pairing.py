# -*- coding: utf-8 -*-
"""详情页 图↔含义 配对回归（68 号单错位事故）。

事故：cmd_get_episode 用 sorted(文件名) × panel 数字序 meanings 的**位置**
配对——中文字典序和 panel 序错开，"生气"行显示融化图、打分键错挂。
修复：_episode_stickers 按含义词反查文件名锁定（与发布端 from_dir 同约定）。
"""
import json

from PIL import Image


def _make_episode(tmp_path, files, meaning_map=None):
    ep = tmp_path / "episode_20260828_174124"
    final = ep / "最终版"
    final.mkdir(parents=True)
    for name in files:
        Image.new("RGBA", (240, 240), (255, 0, 0, 255)).save(final / f"{name}.png")
    if meaning_map is not None:
        (ep / "meaning_map.json").write_text(
            json.dumps(meaning_map, ensure_ascii=False), encoding="utf-8")
    return ep


def test_pairing_locked_by_name_not_position(tmp_path):
    """字典序 ≠ panel 序时（68 号单精简复刻），图词必须按名字对上。"""
    from sticker_engine.cli import _episode_stickers
    # 文件名字典序：傲娇 < 欢呼 < 恳求 < 生气 < 石化 < 融化 < 震惊
    # panel 序（meaning_map 数字序）：欢呼(1) 石化(9) 傲娇(10) 融化(11) 震惊(12) 生气(14) 恳求(16)
    ep = _make_episode(
        tmp_path,
        ["傲娇", "欢呼", "恳求", "生气", "石化", "融化", "震惊"],
        {"1": "欢呼", "9": "石化", "10": "傲娇", "11": "融化",
         "12": "震惊", "14": "生气", "16": "恳求"})
    stickers = _episode_stickers(ep)
    # 每个含义词配到同名文件（旧代码这里会 傲娇.png↔欢呼 等系统性错开）
    assert {s["meaning"]: s["file"] for s in stickers} == {
        "欢呼": "欢呼.png", "石化": "石化.png", "傲娇": "傲娇.png",
        "融化": "融化.png", "震惊": "震惊.png", "生气": "生气.png",
        "恳求": "恳求.png"}
    # 顺序按 meaning_map 数字序（与发布端一致）
    assert [s["meaning"] for s in stickers] == [
        "欢呼", "石化", "傲娇", "融化", "震惊", "生气", "恳求"]


def test_files_missing_from_map_not_dropped(tmp_path):
    """map 没覆盖的文件（改名后 map 未同步）按文件名补齐，不丢图。"""
    from sticker_engine.cli import _episode_stickers
    ep = _make_episode(tmp_path, ["欢呼", "新含义"],
                       {"1": "欢呼"})
    stickers = _episode_stickers(ep)
    assert {s["meaning"] for s in stickers} == {"欢呼", "新含义"}
    assert len(stickers) == 2


def test_no_map_falls_back_to_sorted_stems(tmp_path):
    """无 meaning_map：stem 排序配对（此时位置==名字，天然不错位）。"""
    from sticker_engine.cli import _episode_stickers
    ep = _make_episode(tmp_path, ["傲娇", "欢呼"], None)
    stickers = _episode_stickers(ep)
    assert [s["meaning"] for s in stickers] == ["傲娇", "欢呼"]


def test_get_episode_uses_name_locked_pairing(tmp_path, monkeypatch):
    """cmd_get_episode 端到端：贴纸 meaning 必须与文件同名（用户看到的就是对的）。"""
    import sticker_engine.cli as cli
    from sticker_engine.cli import cmd_get_episode
    results = []
    # monkeypatch 保证测试后恢复，避免污染后续用例的 _result/_emit 链
    monkeypatch.setattr(
        cli, "_result",
        lambda req_id, status, data=None, **kw: results.append(
            (status, data if data is not None else kw)))
    ep = _make_episode(
        tmp_path,
        ["傲娇", "欢呼", "生气", "融化", "震惊"],
        {"1": "欢呼", "10": "傲娇", "11": "融化", "12": "震惊", "14": "生气"})
    cmd_get_episode("req-test", {"episode_dir": str(ep)})
    [(status, data)] = results
    assert status == "ok"
    for s in data["stickers"]:
        assert s["meaning"] == s["file"][:-4]  # 图和词一致，用户打分键才可信
