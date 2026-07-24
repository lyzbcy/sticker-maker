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
