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
