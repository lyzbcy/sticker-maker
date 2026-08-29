"""run 成功后自动按默认系列编号命名的集成测试 + 发布前置名称校验测试。"""
import json
from pathlib import Path

import pytest

from sticker_engine.config.series import (
    Series, save_series, load_series, load_meta, _series_file)


@pytest.fixture(autouse=True)
def _isolated_series(tmp_path, monkeypatch):
    import sticker_engine.config.series as series_mod
    monkeypatch.setattr(series_mod, "_series_file", lambda: tmp_path / "series.json")
    return tmp_path


def _build_config(tmp_path):
    from sticker_engine import Config
    from sticker_engine.config.schema import Paths, Prefs
    config = Config.placeholder()
    config.paths = Paths(
        user_data=tmp_path, output_root=tmp_path / "e", reference_lib=tmp_path / "ref",
        prefs_file=tmp_path / "p.yaml", codex_exec="codex", codex_output_dir=tmp_path / "c")
    return config


def test_run_auto_names_album_with_default_series(tmp_path):
    """prefs.default_series_id 设置时，run 成功自动生成「系列名 编号」专辑名。"""
    from sticker_engine import StickerEngine
    config = _build_config(tmp_path)
    # 建系列 + 设为默认
    s = Series(id="zh", name="周思涵做表情", start_number=60)
    save_series([s])
    config.prefs.default_series_id = "zh"

    engine = StickerEngine(config)
    engine._inject_test_mocks()
    episode = engine.run()

    assert episode.success is True
    meta = load_meta(Path(episode.episode_dir))
    assert meta.album_name == "周思涵做表情60"
    assert meta.series_id == "zh"
    # 系列编号已推进（下一个 61）
    assert load_series()[0].next_number == 61

    # 第二次 run → 61
    engine2 = StickerEngine(config)
    engine2._inject_test_mocks()
    ep2 = engine2.run()
    assert ep2.success is True
    meta2 = load_meta(Path(ep2.episode_dir))
    assert meta2.album_name == "周思涵做表情61"


def test_run_without_default_series_keeps_timestamp_name(tmp_path):
    """未设默认系列：不自动命名（meta.album_name 空，发布时会被前置校验拦住）。"""
    from sticker_engine import StickerEngine
    config = _build_config(tmp_path)
    engine = StickerEngine(config)
    engine._inject_test_mocks()
    episode = engine.run()
    assert episode.success is True
    meta = load_meta(Path(episode.episode_dir))
    assert meta.album_name == ""


def _call(handler, args):
    results = []
    import sticker_engine.cli as cli
    orig = cli._result
    cli._result = lambda req_id, status, data=None, **kw: results.append(
        (status, data if data is not None else kw))
    try:
        handler("req-t", args)
    finally:
        cli._result = orig
    return results


def test_publish_blocked_for_unnamed_episode(tmp_path):
    """发布前置校验：时间戳名/空名 → 阻断并给指引。"""
    from sticker_engine.cli import cmd_publish_episode
    from PIL import Image
    ep = tmp_path / "episode_20260825_220451"
    (ep / "最终版").mkdir(parents=True)
    Image.new("RGBA", (240, 240), (255, 0, 255)).save(ep / "最终版" / "开心.png")

    [(status, data)] = _call(cmd_publish_episode, {"episode_dir": str(ep)})
    assert status == "fail"
    assert "还没有正式命名" in data["error"]
    assert "详情页" in data["error"]   # 指引到详情页
