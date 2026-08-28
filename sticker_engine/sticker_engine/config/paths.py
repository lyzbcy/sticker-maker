import os
import sys
from pathlib import Path
from .schema import Paths


def _app_data_dir(platform: str, app_name: str) -> Path:
    """解析 OS 标准用户数据目录。不写死任何盘符。"""
    if platform == "darwin":
        home = os.path.expanduser("~")
        return Path(home) / "Library" / "Application Support" / app_name
    elif platform == "win32":
        # %APPDATA% 由系统定义，用 expandvars 解析，不写死 C:\
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(appdata) / app_name
    else:  # linux 等
        xdg = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        return Path(xdg) / app_name


def _codex_output_dir() -> Path:
    """codex 生成图落在 ~/.codex/generated_images/（Mac/Linux），Win 类似。"""
    home = os.path.expanduser("~")
    return Path(home) / ".codex" / "generated_images"


def resolve_paths(platform: str, app_name: str = "StickerEngine") -> Paths:
    # 测试隔离口（也方便高级用户整体搬数据目录）：
    # STICKER_ENGINE_USER_DATA 指定后，全部用户数据（episodes/prefs/…）随之迁移
    override = os.environ.get("STICKER_ENGINE_USER_DATA")
    user_data = Path(override) if override else _app_data_dir(platform, app_name)
    return Paths(
        user_data=user_data,
        output_root=user_data / "episodes",
        reference_lib=user_data / "reference_library",
        prefs_file=user_data / "prefs.yaml",
        codex_exec="codex",   # 依赖 PATH 查找；用户可在 prefs 覆盖
        codex_output_dir=_codex_output_dir(),
    )


def current_platform() -> str:
    return sys.platform
