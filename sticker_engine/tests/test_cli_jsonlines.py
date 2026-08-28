import json
import os
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


# ---- C1 集成验证：custom_bases 真挂进角色 ----
def test_add_base_then_list_shows_custom_character(tmp_path, monkeypatch):
    """add_base 后 list_characters 能看到'自定义'角色。"""
    from sticker_engine import cli
    from PIL import Image
    # 造一张假 base 图
    src = tmp_path / "my_base.png"
    Image.new("RGBA", (10, 10)).save(src)
    # mock engine 的 paths
    fake_engine = MagicMock()
    fake_engine.config.paths.user_data = tmp_path
    fake_engine.config.characters = {}
    monkeypatch.setattr(cli, "_engine", fake_engine)
    monkeypatch.setattr(cli, "_emit", lambda ev: None)
    # add_base
    cli.cmd_add_base("r1", {"path": str(src)})
    # custom_bases 目录应存在 + 文件在
    assert (tmp_path / "custom_bases" / "自定义" / "my_base.png").exists()
    # _sync 后"自定义"角色应挂上
    cli._sync_custom_bases(fake_engine)
    assert "自定义" in fake_engine.config.characters
    assert "my_base" in fake_engine.config.characters["自定义"].bases


def test_add_base_assigns_image_to_named_character(tmp_path, monkeypatch):
    from sticker_engine import cli
    from PIL import Image

    src = tmp_path / "my_base.png"
    Image.new("RGBA", (10, 10)).save(src)
    fake_engine = MagicMock()
    fake_engine.config.paths.user_data = tmp_path
    fake_engine.config.characters = {}
    fake_engine.config.prefs.base_probs = {}
    monkeypatch.setattr(cli, "_engine", fake_engine)
    monkeypatch.setattr(cli, "_emit", lambda ev: None)

    cli.cmd_add_base("r1", {"path": str(src), "character": "小星"})
    cli._sync_custom_bases(fake_engine)

    assert (tmp_path / "custom_bases" / "小星" / "my_base.png").exists()
    assert "小星" in fake_engine.config.characters


def test_add_base_rejects_path_like_character_name(tmp_path, monkeypatch):
    from sticker_engine import cli
    from PIL import Image

    src = tmp_path / "my_base.png"
    Image.new("RGBA", (10, 10)).save(src)
    fake_engine = MagicMock()
    fake_engine.config.paths.user_data = tmp_path
    fake_engine.config.characters = {}
    monkeypatch.setattr(cli, "_engine", fake_engine)
    emitted = []
    monkeypatch.setattr(cli, "_emit", emitted.append)

    cli.cmd_add_base("r1", {"path": str(src), "character": "../逃逸"})

    assert emitted[-1]["status"] == "fail"
    assert not (tmp_path / "逃逸").exists()


def test_memory_logs_keep_only_last_50_entries():
    from sticker_engine import cli

    cli._memory_logs.clear()
    for i in range(60):
        cli._log("info", f"event-{i}")

    logs = cli._safe_logs()
    assert len(logs) == 50
    assert logs[0]["message"] == "event-10"
    assert logs[-1]["message"] == "event-59"


def test_memory_logs_strip_sensitive_metadata():
    from sticker_engine import cli

    cli._memory_logs.clear()
    cli._log(
        "info",
        "agent ready",
        token="secret-token",
        password="secret-password",
        port=7432,
    )

    serialized = json.dumps(cli._safe_logs())
    assert "secret-token" not in serialized
    assert "secret-password" not in serialized
    assert "7432" in serialized


def test_get_and_clear_logs_commands(monkeypatch):
    from sticker_engine import cli

    cli._memory_logs.clear()
    cli._log("info", "hello")
    emitted = []
    monkeypatch.setattr(cli, "_emit", emitted.append)

    cli.cmd_get_logs("get", {})
    assert emitted[-1]["data"]["logs"][-1]["message"] == "hello"

    cli.cmd_clear_logs("clear", {})
    assert emitted[-1]["status"] == "ok"
    assert cli._safe_logs() == []


def test_publish_episode_command_returns_structured_result(tmp_path, monkeypatch):
    from sticker_engine import cli

    episode_dir = tmp_path / "一弹"
    episode_dir.mkdir()
    # 发布前置校验要求正式命名（时间戳/空名会被拦截），写 meta
    (episode_dir / "meta.json").write_text(
        '{"album_name": "一弹"}', encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "_publish_episode",
        lambda episode_dir, progress: {
            "success": True,
            "step": "done",
            "album_name": Path(episode_dir).name,
        },
    )
    emitted = []
    monkeypatch.setattr(cli, "_emit", emitted.append)

    cli.cmd_publish_episode("publish-1", {"episode_dir": str(episode_dir)})

    result = emitted[-1]
    assert result["type"] == "result"
    assert result["status"] == "ok"
    assert result["data"]["album_name"] == "一弹"


def test_publish_episode_requires_existing_directory(monkeypatch):
    from sticker_engine import cli

    emitted = []
    monkeypatch.setattr(cli, "_emit", emitted.append)

    cli.cmd_publish_episode("publish-2", {"episode_dir": "/missing/episode"})

    assert emitted[-1]["status"] == "fail"
    assert "不存在" in emitted[-1]["errors"][0]["message"]


def test_agent_service_start_is_idempotent_and_stoppable():
    from sticker_engine import cli

    cli._stop_agent_server()
    first = cli._start_agent_server(port=0)
    try:
        second = cli._start_agent_server(port=0)
        assert first["running"] is True
        assert second["already_running"] is True
        assert first["token"] == second["token"]
        assert first["port"] > 0
    finally:
        stopped = cli._stop_agent_server()
    assert stopped["running"] is False


def test_list_characters_returns_absolute_preview_paths(tmp_path, monkeypatch):
    from sticker_engine import cli
    from sticker_engine.config.schema import Character

    fake_engine = MagicMock()
    fake_engine.config.paths.user_data = tmp_path
    fake_engine.config.characters = {
        "甲": Character(
            name="甲",
            bases={"a": "base_images/星星布丁/base1.jpg"},
            base_probs={"a": 1.0},
        ),
    }
    fake_engine.config.prefs.base_probs = {}
    emitted = []
    monkeypatch.setattr(cli, "_engine", fake_engine)
    monkeypatch.setattr(cli, "_emit", emitted.append)

    cli.cmd_list_characters("chars", {})

    preview = emitted[-1]["data"]["characters"]["甲"]["bases"]["a"]
    assert Path(preview).is_absolute()
    # 路径分隔符跨平台：posix 为 /，Windows 为 \
    expected = os.path.join("base_images", "星星布丁", "base1.jpg")
    assert preview.endswith(expected)
