from dataclasses import dataclass, field
from collections import deque
from pathlib import Path
from typing import Optional

LOG_CAPACITY = 50


@dataclass
class ModeProbs:
    single: float = 0.5
    duo: float = 0.3
    trio: float = 0.0
    quad: float = 0.2

    def sum(self) -> float:
        return self.single + self.duo + self.trio + self.quad


@dataclass
class EpisodeSpec:
    """本次 run 的用户意图。"""
    mode_probs: ModeProbs = field(default_factory=ModeProbs)
    forced_characters: Optional[list] = None   # 指定角色（None=按概率抽）
    forced_mode: Optional[str] = None          # "single"/"duo"/"trio"/"quad"（None=按概率抽）
    grid_size: int = 4                         # 4/3/2/1
    transparent_default: bool = True           # prompt 模式默认透明
    story_mode: bool = True
    ref_lib_priority: bool = True

    @classmethod
    def placeholder(cls):
        return cls()


@dataclass
class LogEntry:
    stage: str          # "S0"/"S1"/"S2"/"S3"
    status: str         # "OK"/"WARN"/"FAIL"
    message: str
    timestamp: float = 0.0   # time.time()，默认 0 方便测试


@dataclass
class ProgressEvent:
    stage: str
    phase: str
    message: str
    percent: float
    eta_seconds: Optional[int] = None

    def __post_init__(self):
        if self.percent > 1.0:
            self.percent = 1.0
        elif self.percent < 0.0:
            self.percent = 0.0


@dataclass
class GateError:
    gate: str
    message: str
    guidance: str = ""


@dataclass
class PipelineContext:
    config: object
    episode: EpisodeSpec
    episode_dir: Optional[Path] = None
    grid_image: Optional[Path] = None
    stickers: list = field(default_factory=list)
    meaning_map: dict = field(default_factory=dict)
    assets: object = None
    _production_log: deque = field(default_factory=lambda: deque(maxlen=LOG_CAPACITY))
    errors: list = field(default_factory=list)

    @property
    def production_log(self) -> list:
        return list(self._production_log)

    def log(self, entry: LogEntry) -> None:
        self._production_log.append(entry)

    def add_error(self, err: GateError) -> None:
        self.errors.append(err)
