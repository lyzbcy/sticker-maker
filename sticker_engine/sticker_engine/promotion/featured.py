"""精选表情管理（初心第 85 行：软件里多用精选）。

内置 138 张精选表情（resources/featured/），软件内多处展示：
- 主界面轮播
- 结果页"你可能还喜欢"
"""
import random
from pathlib import Path
from typing import Optional
import sys


def _featured_dir() -> Path:
    """精选表情目录（兼容 PyInstaller 打包）。"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "featured"
    # 开发模式：从 promotion 包往上找 resources
    return Path(__file__).resolve().parent.parent / "resources" / "featured"


def list_featured() -> list:
    """返回全部精选表情路径。无则空列表。"""
    d = _featured_dir()
    if not d.exists():
        return []
    return sorted(d.glob("*.png"))


def sample_featured(n: int = 8, seed: Optional[int] = None) -> list:
    """随机抽 n 张精选。n 大于总数时返回全部。"""
    all_featured = list_featured()
    if len(all_featured) <= n:
        return all_featured
    rng = random.Random(seed)
    return rng.sample(all_featured, n)


def featured_count() -> int:
    """精选总数。"""
    return len(list_featured())
