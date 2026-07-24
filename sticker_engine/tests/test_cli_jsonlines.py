import json
import subprocess
import sys
from pathlib import Path


def _run_cli(commands):
    """启动 cli 子进程，喂命令，收集 stdout 行。"""
    proc = subprocess.Popen(
        [sys.executable, "-m", "sticker_engine.cli"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=Path(__file__).parent.parent)
    stdin_data = "\n".join(json.dumps(c) for c in commands) + "\n"
    stdout, stderr = proc.communicate(input=stdin_data, timeout=30)
    return [json.loads(line) for line in stdout.strip().split("\n") if line.strip()], stderr


def test_check_codex_command_returns_result():
    lines, _ = _run_cli([{"id": "r1", "cmd": "check_codex"}])
    results = [l for l in lines if l.get("id") == "r1" and l.get("type") == "result"]
    assert len(results) == 1
    assert results[0]["status"] in ("ok", "fail")
    assert "data" in results[0] or "errors" in results[0]


def test_get_version_returns_version_string():
    lines, _ = _run_cli([{"id": "r2", "cmd": "get_version"}])
    results = [l for l in lines if l.get("id") == "r2" and l.get("type") == "result"]
    assert len(results) == 1
    assert results[0]["status"] == "ok"
    assert "version" in results[0]["data"]


def test_unknown_cmd_returns_error_event():
    lines, _ = _run_cli([{"id": "r3", "cmd": "nonsense_cmd"}])
    errors = [l for l in lines if l.get("id") == "r3" and l.get("type") == "error"]
    assert len(errors) == 1
    assert "message" in errors[0]


def test_stdout_contains_only_json_lines():
    """协议纪律：stdout 严格只 JSON，无杂散 print。"""
    lines, stderr = _run_cli([{"id": "r4", "cmd": "get_version"}])
    assert all(isinstance(l, dict) for l in lines)


# ---- Task 2: run progress 流 + stop 中断 ----
import threading
import time
from unittest.mock import MagicMock
from pathlib import Path as _Path


def test_run_emits_progress_events_via_mock_engine(monkeypatch):
    """run 命令持续吐 progress + 最终 result（mock engine 避免真实 codex）。"""
    from sticker_engine import cli
    from sticker_engine import Episode
    from sticker_engine.pipeline.context import ProgressEvent

    fake_engine = MagicMock()
    def fake_run(progress_callback=None, stop_event=None):
        for i, pct in enumerate([0.3, 0.6, 1.0]):
            progress_callback(ProgressEvent(stage="S1", phase="x", message=f"m{i}",
                                           percent=pct, eta_seconds=180))
        return Episode(success=True, episode_dir=_Path("/tmp/fake"),
                       stickers=[1]*16, meaning_map={i: f"含义{i}" for i in range(1,17)})
    fake_engine.run = fake_run
    fake_engine.config.paths.prefs_file = _Path("/tmp/nonexist_prefs.yaml")
    monkeypatch.setattr(cli, "_engine", fake_engine)

    emitted = []
    monkeypatch.setattr(cli, "_emit", lambda ev: emitted.append(ev))
    cli.cmd_run("req-run", {})
    progress_events = [e for e in emitted if e["type"] == "progress"]
    result_events = [e for e in emitted if e["type"] == "result"]
    assert len(progress_events) == 3
    assert result_events[0]["status"] == "ok"
    assert result_events[0]["data"]["stickers"] == 16


def test_stop_command_sets_stop_event(monkeypatch):
    """stop 命令能置位对应 run 的 stop_event。"""
    from sticker_engine import cli

    captured_stop = {}
    fake_engine = MagicMock()
    def fake_run(progress_callback=None, stop_event=None):
        captured_stop["event"] = stop_event
        stop_event.wait(timeout=2)
        return __import__("sticker_engine", fromlist=["Episode"]).Episode(success=False, aborted_reason="用户取消")
    fake_engine.run = fake_run
    fake_engine.config.paths.prefs_file = _Path("/tmp/x.yaml")
    monkeypatch.setattr(cli, "_engine", fake_engine)
    monkeypatch.setattr(cli, "_emit", lambda ev: None)

    t = threading.Thread(target=cli.cmd_run, args=("req-s", {}))
    t.start()
    for _ in range(100):
        if "req-s" in cli._stop_events:
            break
        time.sleep(0.02)
    cli.cmd_stop("req-stop", {"target_id": "req-s"})
    t.join(timeout=3)
    assert captured_stop["event"].is_set()
