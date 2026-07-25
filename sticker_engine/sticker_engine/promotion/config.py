"""三码推广配置（赞赏/入群/表情包二维码）。

参考 lyzbcy-study-map 的推广设计。
默认使用随软件分发的捞鱼三码，也支持用户本地覆盖。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _bundled_qr(name: str) -> Path:
    from .. import resources_path
    return resources_path() / "promotion" / name


@dataclass
class PromotionConfig:
    """三码配置。默认展示随软件分发的捞鱼推广资源。"""
    reward_qr: Optional[Path] = field(
        default_factory=lambda: _bundled_qr("reward-qr.jpg"))
    group_qr: Optional[Path] = field(
        default_factory=lambda: _bundled_qr("qq-group.jpg"))
    sticker_qr: Optional[Path] = field(
        default_factory=lambda: _bundled_qr("sticker-qr.png"))
    author_name: str = "捞鱼真不吃鱼"     # 署名

    def has_any(self) -> bool:
        """是否有任一二维码配置（决定 About 页是否展示推广区）。"""
        return any([self.reward_qr, self.group_qr, self.sticker_qr])

    def validate(self) -> list:
        """校验已配置的二维码文件存在，返回缺失列表。"""
        missing = []
        for label, p in [("reward", self.reward_qr), ("group", self.group_qr), ("sticker", self.sticker_qr)]:
            if p is not None and not Path(p).exists():
                missing.append(label)
        return missing
