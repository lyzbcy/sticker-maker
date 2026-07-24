"""发布配置（固定值 + 赞赏图路径 + 登录凭据）。

迁移自现有 publisher skill 的"固定配置速查"。
赞赏图默认用捞鱼的，支持自定义（spec 决策 A）。
登录从 .env 读（base64 密码，迁移现有机制）。
"""
import base64
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _default_tip_guide() -> Path:
    """默认赞赏引导图：优先项目根的赞赏页/赞赏引导图.png。"""
    # 从 publish 包往上找到项目根（微信表情包/）
    root = Path(__file__).resolve().parents[3]
    return root / "赞赏页" / "赞赏引导图.png"


def _default_tip_thanks() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "赞赏页" / "赞赏致谢图.png"


def _default_storage_state() -> Path:
    """登录态持久化路径（Mac 标准 Application Support）。"""
    home = os.path.expanduser("~")
    return Path(home) / "Library" / "Application Support" / "StickerEngine" / "publish_storage.json"


@dataclass
class PublishConfig:
    # 固定配置（迁移自现有 skill）
    copyright: str = "捞鱼真不吃鱼"
    thanks_text: str = "谢谢你喜欢我~"
    category: str = "卡通表情/其他"
    style: list = field(default_factory=lambda: ["软萌可爱", "日常"])
    theme: str = "万能通用"
    region: str = "全球"
    accept_tips: bool = True

    # 赞赏图（默认捞鱼的，可自定义）
    tip_guide_img: Path = field(default_factory=_default_tip_guide)
    tip_thanks_img: Path = field(default_factory=_default_tip_thanks)

    # 登录
    account: Optional[str] = None
    password: Optional[str] = None   # 明文（从 .env base64 解码）
    storage_state: Path = field(default_factory=_default_storage_state)

    # 超时
    navigation_timeout_ms: int = 60000
    action_timeout_ms: int = 15000

    @classmethod
    def from_env(cls, env_path: Optional[Path] = None) -> "PublishConfig":
        """从 .env 读账号密码（WECHAT_STICKER_ACCOUNT + WECHAT_STICKER_PASSWORD_ENCODED base64）。

        迁移现有 publisher 的 .env 机制：
        WECHAT_STICKER_ACCOUNT=lyzbcy@qq.com
        WECHAT_STICKER_PASSWORD_ENCODED=<base64>
        """
        cfg = cls()
        # 找 .env：优先 env_path，再项目根，再 publisher skill 目录
        candidates = []
        if env_path:
            candidates.append(Path(env_path))
        root = Path(__file__).resolve().parents[3]
        candidates.append(root / ".env")
        candidates.append(root / ".openclaw" / "skills" / "lyzbcy-sticker-publisher" / "scripts" / ".env")

        for p in candidates:
            if p.exists():
                _load_dotenv(p, cfg)
                break
        return cfg

    def validate_tips_images(self) -> list:
        """校验赞赏图存在，返回缺失列表。"""
        missing = []
        if not self.tip_guide_img.exists():
            missing.append(str(self.tip_guide_img))
        if not self.tip_thanks_img.exists():
            missing.append(str(self.tip_thanks_img))
        return missing


def _load_dotenv(path: Path, cfg: "PublishConfig") -> None:
    """简易 .env 解析（KEY=VALUE）。"""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k == "WECHAT_STICKER_ACCOUNT":
            cfg.account = v
        elif k == "WECHAT_STICKER_PASSWORD_ENCODED":
            try:
                cfg.password = base64.b64decode(v).decode("utf-8")
            except Exception:
                cfg.password = v   # 非 base64，当明文
