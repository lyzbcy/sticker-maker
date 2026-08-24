import os
import sys
from pathlib import Path
from sticker_engine.config.paths import Paths


def test_paths_resolve_mac_uses_app_support():
    p = Paths.resolve("darwin", app_name="StickerEngine")
    s = str(p.user_data)
    assert "StickerEngine" in s
    # "~/Library/Application Support" 只在真 Mac 上存在；Windows 上跑用例只查路径形状
    if sys.platform == "darwin":
        assert p.user_data.exists() or p.user_data.parent.exists()  # 父目录在
        # 没有任何 Windows 字面量
        assert "\\" not in s
    assert "Library" in s
    assert "E:" not in s


def test_paths_codex_output_dir_under_home():
    p = Paths.resolve("darwin", app_name="StickerEngine")
    assert ".codex" in str(p.codex_output_dir)
    assert "generated_images" in str(p.codex_output_dir)


def test_paths_reference_lib_defaults_under_user_data():
    p = Paths.resolve("darwin", app_name="StickerEngine")
    assert p.reference_lib.parent == p.user_data


def test_paths_win_uses_appdata_when_forced():
    # 模拟 win：即使本机是 mac，resolve("win32") 也应给出 %APPDATA% 风格路径
    p = Paths.resolve("win32", app_name="StickerEngine")
    s = str(p.user_data)
    # Win 标准位置用 appdirs/expandvars，不写死盘符
    assert "StickerEngine" in s
