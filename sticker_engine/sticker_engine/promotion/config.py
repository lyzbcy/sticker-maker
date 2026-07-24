"""三码推广配置（赞赏/入群/表情包二维码）。

参考 lyzbcy-study-map 的推广设计。
默认全 None（粉丝软件不展示开发者私人码）。开发者本地配置后显示。
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PromotionConfig:
    """三码配置。默认空，开发者（捞鱼）本地填。"""
    reward_qr: Optional[Path] = None     # 赞赏二维码
    group_qr: Optional[Path] = None      # 入群二维码
    sticker_qr: Optional[Path] = None    # 表情包下载二维码
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
