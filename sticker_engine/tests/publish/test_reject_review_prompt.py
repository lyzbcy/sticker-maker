# -*- coding: utf-8 -*-
"""驳回评审 prompt 命令测试（一键复制交给 AI 分析驳回原因）。"""
import json
from pathlib import Path

import sticker_engine.cli as cli
from sticker_engine.cli import cmd_build_reject_review_prompt


def _call(args):
    results = []
    orig = cli._result
    cli._result = lambda req_id, status, data=None, **kw: results.append(
        (status, data if data is not None else kw))
    try:
        cmd_build_reject_review_prompt("req-test", args)
    finally:
        cli._result = orig
    return results[0]


def _make_ep(tmp_path, monkeypatch, reason):
    ep = tmp_path / "episode_test"
    (ep / "原图").mkdir(parents=True)
    from sticker_engine.config.series import load_meta, save_meta
    m = load_meta(ep)
    m.album_name = "周三涵做表情 65"
    m.platform_reject_reason = reason
    save_meta(ep, m)
    (ep / "原图" / "prompt.txt").write_text(
        "# mode: keyword_combo\n# prompt_set: builtin (萌系)\nSTYLE: oversized head", encoding="utf-8")
    # _ensure_engine 指向临时 user_data（prompts 路径不碰真实目录）
    monkeypatch.setattr(cli, "_ensure_engine", lambda: type("E", (), {
        "config": type("C", (), {"paths": type("P", (), {
            "user_data": tmp_path})()})()})())
    return ep


def test_prompt_contains_reason_and_pipeline_context(tmp_path, monkeypatch):
    reason = "聊天页图标在手机上展示位置较小，请去除不必要的文字信息和装饰图案。"
    ep = _make_ep(tmp_path, monkeypatch, reason)
    status, data = _call({"episode_dir": str(ep)})
    assert status == "ok"
    t = data["text"]
    assert reason in t                       # 平台理由原文在内
    assert "oversized head" in t             # 当次生图 prompt 在内
    assert "50x50" in t                      # 管线背景知识（图标缩放根因）
    assert "你的任务" in t


def test_prompt_fails_without_reason(tmp_path, monkeypatch):
    ep = _make_ep(tmp_path, monkeypatch, "")
    status, _ = _call({"episode_dir": str(ep)})
    assert status == "fail"
