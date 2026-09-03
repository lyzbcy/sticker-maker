# -*- coding: utf-8 -*-
"""run_batch 命令测试：count 循环 + auto_publish 分支。"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import sticker_engine.cli as cli
from sticker_engine.cli import cmd_run_batch


class _Ep:
    def __init__(self, ok=True, ep_dir=None, stickers=16):
        self.success = ok
        self.episode_dir = Path(ep_dir) if ep_dir else None
        self.stickers = [1] * stickers
        self.errors = []
        self.aborted_reason = ""
        self.icon_fallback = False


def _call(args, runs, publishes=None, name=None):
    results = []
    orig_result, orig_emit = cli._result, cli._emit
    cli._result = lambda rid, st, data=None, **kw: results.append((st, data))
    cli._emit = lambda ev: None
    engine = MagicMock()
    engine.run.side_effect = runs
    engine.config.prefs.default_series_id = "s1" if name else None
    with patch.object(cli, "_ensure_engine", return_value=engine), \
         patch.object(cli, "_sync_custom_bases"), \
         patch.object(cli, "_publish_episode",
                      side_effect=publishes or []):
        try:
            cmd_run_batch("r", args)
        finally:
            cli._result, cli._emit = orig_result, orig_emit
    return results[0]


def test_batch_runs_count_times(tmp_path):
    st, data = _call({"count": 3, "auto_publish": False},
                     runs=[_Ep(True, tmp_path / "e1"), _Ep(True, tmp_path / "e2"),
                           _Ep(True, tmp_path / "e3")])
    assert st == "ok"
    assert data["requested"] == 3 and data["generated_ok"] == 3
    assert len(data["results"]) == 3


def test_batch_failure_does_not_stop_next(tmp_path):
    st, data = _call({"count": 2, "auto_publish": False},
                     runs=[_Ep(False), _Ep(True, tmp_path / "e2")])
    assert st == "ok"
    assert data["generated_ok"] == 1
    assert data["results"][0]["error"]


def test_auto_publish_requires_default_series(tmp_path):
    st, data = _call({"count": 1, "auto_publish": True},
                     runs=[_Ep(True, tmp_path / "e1")], name=None)
    assert data["results"][0].get("publish_skip")


def test_auto_publish_skips_icon_fallback(tmp_path):
    """2026-09 图标降级风险：AI 图标失败退回复用封面（曾致平台驳回）→
    该单跳过自动发布，结果标注「图标生成失败，未发布」。"""
    results = []
    orig_result, orig_emit = cli._result, cli._emit
    cli._result = lambda rid, st, data=None, **kw: results.append((st, data))
    cli._emit = lambda ev: None
    engine = MagicMock()
    ep = _Ep(True, tmp_path / "e1")
    ep.icon_fallback = True
    engine.run.return_value = ep
    engine.config.prefs.default_series_id = "s1"
    publish = MagicMock()
    try:
        with patch.object(cli, "_ensure_engine", return_value=engine), \
             patch.object(cli, "_sync_custom_bases"), \
             patch.object(cli, "_publish_episode", publish):
            cmd_run_batch("r", {"count": 1, "auto_publish": True})
    finally:
        cli._result, cli._emit = orig_result, orig_emit
    st, data = results[0]
    assert st == "ok"
    item = data["results"][0]
    assert item["published"] is False
    assert "图标生成失败" in item["publish_skip"]
    assert "手动提交" in item["publish_skip"]
    publish.assert_not_called()          # 发布动作一次都没触发
    assert data["published_ok"] == 0


def test_auto_publish_normal_episode_not_blocked_by_icon_flag(tmp_path):
    """对照组：icon_fallback=False 的成功单不被图标降级逻辑拦截（走正常发布分支）。"""
    results = []
    orig_result, orig_emit = cli._result, cli._emit
    cli._result = lambda rid, st, data=None, **kw: results.append((st, data))
    cli._emit = lambda ev: None
    engine = MagicMock()
    engine.run.return_value = _Ep(True, tmp_path / "e1")   # icon_fallback 默认 False
    engine.config.prefs.default_series_id = "s1"
    ep_dir = tmp_path / "e1"; ep_dir.mkdir()
    (ep_dir / "meta.json").write_text('{"album_name": "测试系列 1"}', encoding="utf-8")
    publish = MagicMock(return_value={"success": True})
    try:
        with patch.object(cli, "_ensure_engine", return_value=engine), \
             patch.object(cli, "_sync_custom_bases"), \
             patch.object(cli, "_publish_episode", publish):
            cmd_run_batch("r", {"count": 1, "auto_publish": True})
    finally:
        cli._result, cli._emit = orig_result, orig_emit
    _, data = results[0]
    publish.assert_called_once()
    assert data["results"][0].get("published") is True


def test_batch_circuit_breaker_after_3_fails(tmp_path):
    """熔断：连续 3 组失败自动中止（额度耗尽时空壳刷屏事故）。"""
    st, data = _call({"count": 10, "auto_publish": False},
                     runs=[_Ep(False)] * 10)
    assert st == "ok"
    assert len(data["results"]) == 3   # 第 3 次失败后熔断，不开第 4 组
    assert all(not r["success"] for r in data["results"])
