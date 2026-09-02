from dataclasses import dataclass, field
from collections import deque
from pathlib import Path
from typing import Callable, Optional

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
    # S1 决出的生图模式（传给 S2 决定抠图策略，C1 修复）
    gen_mode: Optional[str] = None   # "ref_library"/"story"/"keyword_combo"
    # S0 选中的 base 图路径（按 base_probs 概率选，I6 修复）
    selected_base: Optional[Path] = None
    # 多人模式下每个选中角色各自的 base，顺序与 selected_characters 一致。
    selected_bases: list = field(default_factory=list)
    # S0 选中的角色列表
    selected_characters: list = field(default_factory=list)
    stickers: list = field(default_factory=list)
    meaning_map: dict = field(default_factory=dict)
    assets: object = None
    # S3 图标降级信号：AI 大头照生成失败、退回复用封面（曾致平台驳回的形态）。
    # 批量自动发布路径据此跳过该单（cli.cmd_run_batch）；单次手动生成不阻断。
    icon_fallback: bool = False
    # S1 进度注入：runner 在每个 stage 执行前设置（签名 (message: str) -> None），
    # stage 内部用它发细粒度进度（做什么 / 输入 / 输出 / 在等什么），stage 外为 None。
    stage_progress: Optional[Callable] = None
    _production_log: deque = field(default_factory=lambda: deque(maxlen=LOG_CAPACITY))
    errors: list = field(default_factory=list)
    # stage 主动中止（如 IP 校验连续不过）：runner 见到即停，不再跑后续 Gate
    # （否则会出现"S1 已明确中止 → Gate1 又报'生图产物缺失'"的迷惑链）
    aborted: bool = False

    @property
    def production_log(self) -> list:
        return list(self._production_log)

    def log(self, entry: LogEntry) -> None:
        self._production_log.append(entry)

    def abort(self, gate: str, message: str, guidance: str = "") -> None:
        """stage 主动中止本单：置 aborted 并记录原因（供结果面板展示）。"""
        self.aborted = True
        self.add_error(GateError(gate=gate, message=message, guidance=guidance))

    def add_error(self, err: GateError) -> None:
        self.errors.append(err)
