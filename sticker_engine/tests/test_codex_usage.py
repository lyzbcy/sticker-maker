"""codex_usage 命令：注册 / 远程成功 / 降级路径 / 本地统计 / token 不泄漏。"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from sticker_engine import cli


def _capture(monkeypatch):
    emitted = []
    monkeypatch.setattr(cli, "_emit", emitted.append)
    fake_engine = MagicMock()
    fake_engine.config.paths.codex_output_dir = Path(__file__).parent / "_no_such_dir"
    monkeypatch.setattr(cli, "_engine", fake_engine)
    return emitted


# ---- 命令注册 ----

def test_codex_usage_registered_in_handlers():
    assert "codex_usage" in cli.HANDLERS
    assert cli.HANDLERS["codex_usage"] is cli.cmd_codex_usage


# ---- 远程成功路径（mock 网络层） ----

def test_codex_usage_remote_success(monkeypatch):
    emitted = _capture(monkeypatch)
    monkeypatch.setattr(cli, "_read_codex_auth",
                        lambda: {"access_token": "fake", "account_id": "acc-1"})
    monkeypatch.setattr(
        cli, "_fetch_codex_remote_usage",
        lambda auth, timeout=15: {
            "plan_type": "plus",
            "rate_limit": {
                "allowed": True, "limit_reached": False,
                "primary_window": {"used_percent": 10, "limit_window_seconds": 18000,
                                   "reset_after_seconds": 18000, "reset_at": 1788374562},
                "secondary_window": {"used_percent": 80, "limit_window_seconds": 604800,
                                     "reset_after_seconds": 394486, "reset_at": 1788751048},
            },
            "credits": {"balance": "0"},
        })

    cli.cmd_codex_usage("req-u1", {})

    result = emitted[-1]
    assert result["type"] == "result"
    assert result["status"] == "ok"
    data = result["data"]
    assert data["available"] is True
    assert data["method"] == "chatgpt_backend_api"
    usage = data["usage"]
    assert usage["plan_display"] == "ChatGPT Plus"
    assert usage["primary_window"]["used_percent"] == 10
    assert usage["primary_window"]["left_percent"] == 90
    assert usage["secondary_window"]["left_percent"] == 20
    assert usage["secondary_window"]["window_hours"] == 168.0
    # reset_at 转成本地可读时间串
    assert "T" in usage["primary_window"]["reset_at"]


# ---- 降级路径：无登录态 → available False + 建议 + 本地统计 ----

def test_codex_usage_falls_back_when_not_logged_in(monkeypatch):
    emitted = _capture(monkeypatch)
    monkeypatch.setattr(cli, "_read_codex_auth", lambda: None)

    cli.cmd_codex_usage("req-u2", {})

    result = emitted[-1]
    assert result["status"] == "ok"          # 命令本身执行成功（协议不炸）
    data = result["data"]
    assert data["available"] is False
    assert data["method"] == "local_images_fallback"
    assert "suggestion" in data
    assert data["local_images"]["today"] == 0


def test_codex_usage_falls_back_on_network_error(monkeypatch):
    emitted = _capture(monkeypatch)
    monkeypatch.setattr(cli, "_read_codex_auth",
                        lambda: {"access_token": "fake", "account_id": "acc-1"})

    def boom(auth, timeout=15):
        raise OSError("network unreachable")

    monkeypatch.setattr(cli, "_fetch_codex_remote_usage", boom)

    cli.cmd_codex_usage("req-u3", {})
    data = emitted[-1]["data"]
    assert data["available"] is False
    assert "network unreachable" in data["error"]
    assert data["local_images"]["total_images"] == 0


# ---- 本地生图统计 ----

def test_count_local_codex_images_by_day(tmp_path):
    from PIL import Image
    now = datetime.now()
    # 今日 2 张、昨天 1 张、8 天前 1 张（超出 7 天窗口不计入逐日）
    def touch(p, dt):
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (4, 4)).save(p)
        import os
        os.utime(p, (dt.timestamp(), dt.timestamp()))
    for i in range(2):
        touch(tmp_path / f"s1/ig_{i}.png", now)
    touch(tmp_path / "s2/ig_x.png", now - timedelta(days=1))
    touch(tmp_path / "s3/ig_old.png", now - timedelta(days=8))
    (tmp_path / "s1/readme.txt").write_text("not an image")

    stats = cli._count_local_codex_images(tmp_path)
    assert stats["today"] == 2
    assert stats["total_images"] == 4          # txt 不算，全历史都算
    day_keys = list(stats["last_7_days"])
    assert len(day_keys) == 2                  # 8 天前不在 7 天窗口
    assert stats["last_7_days"][now.strftime("%Y-%m-%d")] == 2


# ---- 安全：token 绝不出现在命令结果里 ----

def test_codex_usage_result_contains_no_token(monkeypatch):
    emitted = _capture(monkeypatch)
    monkeypatch.setattr(
        cli, "_read_codex_auth",
        lambda: {"access_token": "SUPER_SECRET_TOKEN", "account_id": "acc-1"})
    monkeypatch.setattr(
        cli, "_fetch_codex_remote_usage",
        lambda auth, timeout=15: {"plan_type": "plus", "rate_limit": {}})

    cli.cmd_codex_usage("req-u4", {})
    serialized = json.dumps(emitted, ensure_ascii=False) + json.dumps(cli._safe_logs())
    assert "SUPER_SECRET_TOKEN" not in serialized
    assert emitted[-1]["data"]["available"] is True


# ---- 归一化健壮性：空窗口不炸 ----

def test_normalize_codex_usage_tolerates_missing_windows():
    out = cli._normalize_codex_usage({"plan_type": "free", "rate_limit": {}})
    assert out["plan_display"] == "Free"
    assert out["primary_window"] is None
    assert out["secondary_window"] is None
    assert out["limit_reached"] is False
