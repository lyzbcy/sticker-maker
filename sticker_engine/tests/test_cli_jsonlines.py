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
