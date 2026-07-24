from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from sticker_engine.providers.codex import CodexProvider, CodexStatus


def test_check_returns_not_installed_when_codex_missing(tmp_path):
    provider = CodexProvider(codex_exec="nonexistent_codex_xyz", output_dir=tmp_path)
    status = provider.check()
    assert isinstance(status, CodexStatus)
    assert status.installed is False
    assert status.image_ready is False
    assert len(status.guidance_msg) > 0


def test_scan_latest_image_picks_most_recent(tmp_path):
    # 模拟 codex 输出目录结构：sessions/<id>/*.png
    session = tmp_path / "sess1"
    session.mkdir()
    (session / "old.png").write_bytes(b"x")
    import time
    time.sleep(0.05)
    (session / "new.png").write_bytes(b"y")
    provider = CodexProvider(codex_exec="codex", output_dir=tmp_path)
    latest = provider.scan_latest_image()
    assert latest is not None
    assert latest.name == "new.png"


def test_scan_returns_none_when_no_images(tmp_path):
    provider = CodexProvider(codex_exec="codex", output_dir=tmp_path)
    assert provider.scan_latest_image() is None


def test_build_generate_command_includes_refs_and_prompt(tmp_path):
    provider = CodexProvider(codex_exec="codex", output_dir=tmp_path)
    cmd = provider.build_generate_command(
        prompt="draw a cute sticker",
        refs=[tmp_path/"base.png", tmp_path/"ref1.png"],
    )
    assert "codex" in cmd[0] or cmd[0].endswith("codex")
    assert "--enable" in cmd and "image_generation" in cmd
    assert "-i" in cmd   # 有参考图参数
    assert "draw a cute sticker" in cmd[-1]


def test_exec_text_returns_stdout_string(tmp_path, monkeypatch):
    """exec_text 捕获 codex exec 的 stdout 文本（决策 K：文本任务走 codex）。"""
    provider = CodexProvider(codex_exec="codex", output_dir=tmp_path)

    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = "hello from codex"
            stderr = ""
        return R()

    import sticker_engine.providers.codex as codex_mod
    monkeypatch.setattr(codex_mod.subprocess, "run", fake_run)
    result = provider.exec_text("what is 2+2")
    assert result == "hello from codex"


def test_exec_text_returns_empty_on_failure(tmp_path, monkeypatch):
    """exec_text 失败（非零退出/超时）返回空字符串，不抛异常。"""
    provider = CodexProvider(codex_exec="codex", output_dir=tmp_path)

    def fake_run(cmd, **kw):
        class R:
            returncode = 1
            stdout = ""
            stderr = "error"
        return R()

    import sticker_engine.providers.codex as codex_mod
    monkeypatch.setattr(codex_mod.subprocess, "run", fake_run)
    assert provider.exec_text("prompt") == ""


def test_exec_text_returns_empty_on_timeout(tmp_path, monkeypatch):
    """exec_text 超时返回空字符串（与 generate 的 None 语义对齐，文本侧是空串）。"""
    import subprocess as _sp
    provider = CodexProvider(codex_exec="codex", output_dir=tmp_path)

    def fake_run(cmd, **kw):
        raise _sp.TimeoutExpired(cmd=cmd, timeout=kw.get("timeout", 0))

    import sticker_engine.providers.codex as codex_mod
    monkeypatch.setattr(codex_mod.subprocess, "run", fake_run)
    assert provider.exec_text("prompt") == ""


def test_exec_text_passes_refs_as_i_args(tmp_path, monkeypatch):
    """exec_text 把 refs 作为 -i 参数传入（识图任务 codex 需要看图）。"""
    provider = CodexProvider(codex_exec="codex", output_dir=tmp_path)
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["kw"] = kw

        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""
        return R()

    import sticker_engine.providers.codex as codex_mod
    monkeypatch.setattr(codex_mod.subprocess, "run", fake_run)
    provider.exec_text("describe this", refs=[tmp_path / "big.png"])
    cmd = captured["cmd"]
    assert "-i" in cmd
    assert "image_generation" not in cmd   # 文本任务不开生图 flag
    assert cmd[-1] == "describe this"
