from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import math


def normalize_probs(d: dict) -> dict:
    """把概率字典归一化到 sum=1.0，容忍浮点漂移。空字典返回空。"""
    if not d:
        return d
    total = sum(d.values())
    if total <= 0:
        raise ValueError(f"概率全为 0：{d}")
    return {k: v / total for k, v in d.items()}


@dataclass
class ModeProbsConfig:
    single: float = 0.5
    duo: float = 0.3
    trio: float = 0.0
    quad: float = 0.2


@dataclass
class Character:
    name: str
    bases: dict   # {base_key: path}
    base_probs: dict   # {base_key: prob}，和应为 1.0


@dataclass
class Prefs:
    mode_probs: ModeProbsConfig = field(default_factory=ModeProbsConfig)
    single_char_probs: dict = field(default_factory=dict)
    base_probs: dict = field(default_factory=dict)   # {char: {base_key: prob}}
    grid_size: int = 4
    transparent_default: bool = True
    ref_lib_priority: bool = True
    ref_consume: bool = True     # 参考图=弹药：用过的自动归档（复用会产出雷同贴纸）
    # 故事模式默认关（2026-08-27 定型）：聊天里表情是单发的，四格叙事的
    # "起承转合"与单张贴纸的聊天效用错位；主力=参考图模式，备胎=排列组合。
    # 故事模式保留给"叙事专辑"这种特殊需求，向导里可开。
    story_mode: bool = False
    reference_lib_path: Optional[str] = None   # I2：用户可改参考图库位置（None=默认）
    default_series_id: Optional[str] = None    # 默认系列：run 成功后自动编号命名（None=不自动）
    prompt_set_id: Optional[str] = None        # 默认 Prompt 方案（None=内置萌系大头）
    # 文本调用开关（2026-09-03 用户指令：识图/门禁/文案的文本调用喂图给最强
    # 模型，token 巨大曾把周额度吃光强制卡停）。False=0 token 模式：
    # 含义词直接用生成时选定的词条、门禁跳过、介绍用本地模板。
    vision_calls: bool = False
    # 浏览器模式（2026-09-03 用户需求）：False=有头（默认，能看见软件在
    # 平台上做的每一步），True=无头（后台静默不打扰）。已 A/B/C 实测
    # 微信平台不拦无头浏览器；BrowserSession 仍做 UA 伪装防御未来审查。
    browser_headless: bool = False

    def __post_init__(self):
        s = self.mode_probs.single + self.mode_probs.duo + self.mode_probs.trio + self.mode_probs.quad
        if not math.isclose(s, 1.0, abs_tol=1e-6):
            raise ValueError(f"mode_probs 之和必须为 1.0，当前 {s}")


@dataclass
class Paths:
    user_data: Path
    output_root: Path
    reference_lib: Path
    prefs_file: Path
    codex_exec: str
    codex_output_dir: Path

    @classmethod
    def resolve(cls, platform: str, app_name: str = "StickerEngine") -> "Paths":
        from .paths import resolve_paths
        return resolve_paths(platform, app_name)


@dataclass
class Config:
    characters: dict = field(default_factory=dict)   # {name: Character}
    story_library_path: Optional[Path] = None
    keywords_path: Optional[Path] = None
    magenta_key: str = "#ff00ff"
    green_key: str = "#00ff00"
    prefs: Prefs = field(default_factory=Prefs)
    paths: Optional[Paths] = None

    @classmethod
    def placeholder(cls):
        return cls()
