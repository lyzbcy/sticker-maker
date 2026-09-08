import os
import sys
import json
import re
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
    output_root = user_data / "episodes"
    assets_root = user_data
    device_file = user_data / "resource_library" / "device.json"
    if device_file.exists():
        device = json.loads(device_file.read_text(encoding="utf-8"))
        account, library = device.get("account_id"), device.get("library_id")
        if account and library:
            if not all(re.fullmatch(r"[A-Za-z0-9_-]+", str(v)) for v in (account, library)):
                raise ValueError("资源库设备配置中的身份无效")
            workspace = Path(device.get('workspace_base') or user_data / 'resource_library/workspaces')
            if not workspace.is_absolute():
                raise ValueError('本机工作缓存路径必须是绝对路径')
            output_root = workspace / library / account / "episodes"
            assets_root = workspace / library / account / 'settings'
    return Paths(
        user_data=user_data,
        output_root=output_root,
        reference_lib=assets_root / "reference_library",
        prefs_file=assets_root / "prefs.yaml",
        codex_exec="codex",   # 依赖 PATH 查找；用户可在 prefs 覆盖
        codex_output_dir=_codex_output_dir(),
        assets_root=assets_root,
    )


def current_platform() -> str:
    return sys.platform
