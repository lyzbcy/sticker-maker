"""delete_episode 命令测试：物理删除 + 路径安全 + 编号回滚。

通过真实 CLI 子进程跑（与 test_cli_jsonlines 同 harness），验证：
- 正常删除：文件夹消失、编号回滚（占的是系列最新一号时）
- 中间编号删除：编号不回滚（留空档，防撞号）
- 路径越界：拒绝删除
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run_cli(commands):
    proc = subprocess.Popen(
        [sys.executable, "-m", "sticker_engine.cli"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=Path(__file__).parent.parent.parent)
    stdin_data = "\n".join(json.dumps(c) for c in commands) + "\n"
    stdout, stderr = proc.communicate(input=stdin_data, timeout=30)
    return [json.loads(line) for line in stdout.strip().split("\n") if line.strip()], stderr


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """episode 输出目录与 series.json 都指到临时目录。"""
    out_root = tmp_path / "episodes"
    out_root.mkdir(parents=True)
    series_file = tmp_path / "series.json"
    series_file.write_text(json.dumps([
        {"id": "s1", "name": "测试系列", "start_number": 10, "next_number": 13,
         "intro_prompt": "", "role_asset_map": {}}], ensure_ascii=False), encoding="utf-8")
    # STICKER_ENGINE_USER_DATA：把引擎整个用户数据目录指到临时区（安全隔离）
    monkeypatch.setenv("STICKER_ENGINE_USER_DATA", str(tmp_path))
    return out_root, series_file


def _make_episode(root, name, number):
    ep = root / name
    (ep / "最终版").mkdir(parents=True)
    (ep / "最终版" / "a.png").write_bytes(b"png")
    (ep / "meta.json").write_text(json.dumps({
        "album_name": f"测试系列 {number}", "series_id": "s1",
        "series_name": "测试系列", "number": number, "published": False,
    }, ensure_ascii=False), encoding="utf-8")
    return ep


def test_delete_latest_episode_rolls_back_number(isolated_env):
    root, series_file = isolated_env
    ep11 = _make_episode(root, "episode_a", 11)
    ep12 = _make_episode(root, "episode_b", 12)
    lines, _ = _run_cli([{"id": "r1", "cmd": "delete_episode",
                          "args": {"episode_dir": str(ep12)}}])
    res = [l for l in lines if l.get("id") == "r1" and l.get("type") == "result"][0]
    assert res["status"] == "ok"
    assert not ep12.exists()                      # 物理删除
    assert ep11.exists()                          # 别人不动
    data = json.loads(series_file.read_text(encoding="utf-8"))
    assert data[0]["next_number"] == 12           # 13 → 12 编号回滚
    assert "回滚" not in (res["data"].get("rolled_back") or "") or res["data"]["rolled_back"]


def test_delete_middle_episode_keeps_number(isolated_env):
    """11/12/13 都存在（next=14），删中间的 12 → 编号不回滚（13 还占着，盲回滚会撞号）。"""
    root, series_file = isolated_env
    series_file.write_text(json.dumps([
        {"id": "s1", "name": "测试系列", "start_number": 10, "next_number": 14,
         "intro_prompt": "", "role_asset_map": {}}], ensure_ascii=False), encoding="utf-8")
    _make_episode(root, "episode_a", 11)
    ep12 = _make_episode(root, "episode_b", 12)
    ep13 = _make_episode(root, "episode_c", 13)
    lines, _ = _run_cli([{"id": "r2", "cmd": "delete_episode",
                          "args": {"episode_dir": str(ep12)}}])
    res = [l for l in lines if l.get("id") == "r2" and l.get("type") == "result"][0]
    assert res["status"] == "ok"
    assert not ep12.exists()
    assert ep13.exists()
    assert res["data"].get("rolled_back") is None
    data = json.loads(series_file.read_text(encoding="utf-8"))
    assert data[0]["next_number"] == 14          # 中间号：不回滚


def test_delete_rejects_path_outside_root(isolated_env, tmp_path):
    outside = tmp_path / "outside_episode"
    outside.mkdir()
    lines, _ = _run_cli([{"id": "r4", "cmd": "delete_episode",
                          "args": {"episode_dir": str(outside)}}])
    res = [l for l in lines if l.get("id") == "r4" and l.get("type") == "result"][0]
    assert res["status"] == "fail"
    assert outside.exists()                       # 没被删
