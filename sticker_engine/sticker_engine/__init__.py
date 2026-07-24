import sys
from pathlib import Path

from .api import StickerEngine, Episode
from .config.schema import Config

__all__ = ["StickerEngine", "Episode", "Config", "resources_path"]


def resources_path() -> Path:
    """内置 resources 目录的绝对路径（兼容 PyInstaller 打包）。

    - 开发模式：包目录下的 resources/（<package>/resources）
    - PyInstaller 打包：sys._MEIPASS/resources（--add-data 解压到临时目录）
    """
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller 运行时
        return Path(sys._MEIPASS) / "resources"
    return Path(__file__).parent / "resources"
