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
    story_mode: bool = True

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
