"""发布专辑名回归测试（2026-08-27 事故：平台出现「episode202608251 待审核」）。

根因：EpisodeAssets.from_dir 用 episode_dir.name（时间戳）当专辑名，
没读 meta.json 的正式名。守卫只拦"没命名"，拦不住"命名了但没用上"。
"""
import json
from pathlib import Path

from sticker_engine.publish.publisher import EpisodeAssets


def _make_episode(tmp_path, album_name=None, dir_name="episode_20260825_180912"):
    ep = tmp_path / dir_name
    final = ep / "最终版"
    final.mkdir(parents=True)
    for i, name in enumerate(["开心", "大哭", "睡觉"], 1):
        (final / f"{name}.png").write_bytes(b"png")
    (ep / "meaning_map.json").write_text(
        json.dumps({"1": "开心", "2": "大哭", "3": "睡觉"}, ensure_ascii=False),
        encoding="utf-8")
    if album_name is not None:
        (ep / "meta.json").write_text(
            json.dumps({"album_name": album_name}, ensure_ascii=False), encoding="utf-8")
    return ep


def test_album_name_uses_meta_official_name(tmp_path):
    """meta 有正式名 → 用正式名（不是时间戳目录名）。"""
    ep = _make_episode(tmp_path, album_name="周三涵做表情 61")
    assets = EpisodeAssets.from_dir(ep)
    assert assets.album_name == "周三涵做表情 61"


def test_album_name_falls_back_to_dir_when_no_meta(tmp_path):
    """没有 meta.json → 退回目录名（发布前置校验会拦时间戳名）。"""
    ep = _make_episode(tmp_path, album_name=None)
    assets = EpisodeAssets.from_dir(ep)
    assert assets.album_name == "episode_20260825_180912"


def test_album_name_ignores_timestamp_name_in_meta(tmp_path):
    """meta 里还是时间戳名（未正式命名）→ 不能用它，退回目录名交给守卫拦。"""
    ep = _make_episode(tmp_path, album_name="episode_20260825_180912")
    assets = EpisodeAssets.from_dir(ep)
    assert assets.album_name == "episode_20260825_180912"


def test_album_name_survives_broken_meta(tmp_path):
    """meta.json 损坏 → 静默退回目录名，不崩。"""
    ep = _make_episode(tmp_path, album_name="周三涵做表情 61")
    (ep / "meta.json").write_text("{broken json", encoding="utf-8")
    assets = EpisodeAssets.from_dir(ep)
    assert assets.album_name == "episode_20260825_180912"
