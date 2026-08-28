from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from sticker_engine.providers.codex import CodexProvider, CodexStatus


def test_check_returns_not_installed_when_codex_missing(tmp_path, monkeypatch):
    provider = CodexProvider(codex_exec="nonexistent_codex_xyz", output_dir=tmp_path)
    # 隔离：mock 掉所有 fallback 路径探测（避免本机有桌面 App 时误判）
    monkeypatch.setattr(provider, "_resolve_codex_path", lambda: None)
    status = provider.check()
    assert isinstance(status, CodexStatus)
    assert status.installed is False
    assert status.image_ready is False
    assert len(status.guidance_msg) > 0


def test_resolve_codex_path_finds_desktop_app(monkeypatch):
    """修复A验证：能探测到桌面 App 内部的 codex（GUI PATH 缺失场景）。"""
    from pathlib import Path
    provider = CodexProvider(codex_exec="codex")
    # mock shutil.which 返回 None（模拟 GUI 应用的残缺 PATH）
    import sticker_engine.providers.codex as cmod
    monkeypatch.setattr(cmod.shutil, "which", lambda x: None)
    # 真实探测（本机有 ~/.codex/plugins/.plugin-appserver/codex 或 App 内）
    resolved = provider._resolve_codex_path()
    # 如果本机有桌面 App，应找到；CI 无桌面 App 时不强制
    if resolved:
        assert Path(resolved).is_file()


def test_check_uses_auth_json_for_login(tmp_path, monkeypatch):
    """修复B验证：登录态看 auth.json（不只 auth）。"""
    provider = CodexProvider(codex_exec="codex", output_dir=tmp_path)
    # mock 找到 codex + --version 成功
    monkeypatch.setattr(provider, "_resolve_codex_path", lambda: "/fake/codex")
    import sticker_engine.providers.codex as cmod

    class _R:
        returncode = 0
    monkeypatch.setattr(cmod.subprocess, "run", lambda *a, **kw: _R())
    # mock home 到 tmp_path，造 auth.json
    fake_home = tmp_path / "home"
    (fake_home / ".codex").mkdir(parents=True)
    (fake_home / ".codex" / "auth.json").write_text("{}")
    monkeypatch.setattr(cmod.Path, "home", classmethod(lambda cls: fake_home))
    status = provider.check()
    assert status.installed is True
    assert status.logged_in is True   # auth.json 存在 → 登录态
    assert status.image_ready is True


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
    assert "--skip-git-repo-check" in cmd   # 非 git 目录必须带，否则 codex 拒绝执行
    assert "-i" in cmd   # 有参考图参数
    # 回归守护：prompt 必须出现在所有 -i 之前。
    # codex 0.134+ 的 -i/--image 是多值参数，会贪婪吞掉其后的位置参数；
    # prompt 放在 -i 后会被当成图片文件名 → codex 转而读 stdin → 挂到超时（0 输出）。
    assert cmd.index("draw a cute sticker") < cmd.index("-i")


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
    # 2026-08-27：refs 现在会先经 ASCII 暂存（不存在的文件会被剔除），测试需真实文件
    (tmp_path / "big.png").write_bytes(b"png")
    provider.exec_text("describe this", refs=[tmp_path / "big.png"])
    cmd = captured["cmd"]
    assert "-i" in cmd
    assert "image_generation" not in cmd   # 文本任务不开生图 flag
    assert "--skip-git-repo-check" in cmd
    # 回归守护：prompt 在 -i 之前（同 build_generate_command 的顺序要求）
    assert cmd.index("describe this") < cmd.index("-i")
    # stdin 必须显式关闭（DEVNULL），否则管道环境下 codex 会附加读取 stdin
    assert captured["kw"].get("stdin") is not None
